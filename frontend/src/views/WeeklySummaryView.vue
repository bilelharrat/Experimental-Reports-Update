<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  ExternalLink,
  Loader2,
  RefreshCw,
  TrendingDown,
  TrendingUp,
} from "lucide-vue-next";
import { api } from "../api.js";
import { indexQuoteCards } from "../homeDesk.js";
import { lastPriceLabel, signedChange } from "../liveTicker.js";
import PulseECGIcon from "../components/PulseECGIcon.vue";
import {
  PULSE_INDEX_TICKERS,
  calendarWeekBuckets,
  changedSinceSlice,
  ledgerHitStats,
  macroTapeRows,
  marketBreadthFromUniverse,
  postureFromBreadth,
  pulseQuoteUniverse,
  rankedSignalSlice,
  screenerMoverLists,
  sectorRotationRows,
} from "../marketPulseDesk.js";
import { appLanguage } from "../state.js";
import { useLiveQuotes } from "../useLiveQuotes.js";
import { useT } from "../i18n.js";
import { useLargeTitle } from "../chrome.js";

const t = useT();
const router = useRouter();
const pageTitleEl = ref(null);
useLargeTitle(pageTitleEl);

const loading = ref(true);
const refreshing = ref(false);
const marketLoading = ref(true);
const error = ref(null);
const payload = ref(null);
const refreshDraft = ref(null);
const liveStatus = ref("");
const expandedPrompt = ref(false);
const viewLang = ref(appLanguage.value);
const screeners = ref({ gainers: [], losers: [], active: [], universe: [], sectors: [] });
const calendar = ref({ events: [] });
const signalsPayload = ref(null);
const brief = ref(null);
const briefDates = ref([]);
const briefDate = ref("");
const briefRunning = ref(false);
const briefError = ref("");
const noteWriting = ref(false);
// The extended note is the morning brief proper — tape, central banks,
// geoeconomics and geopolitics. It defaults on; "Short" stays available for
// a quick numbers-only read.
const noteLength = ref("long");

// The morning schedule writes the note on the server, and the long one takes
// ~90s. Without this the page is indistinguishable from "there is no brief".
const noteScheduleRunning = ref(false);
let noteSchedulePoll = null;

const noteBuilding = computed(() => noteWriting.value || noteScheduleRunning.value);

async function pollNoteSchedule() {
  try {
    const state = await api.marketBriefSchedule();
    const wasRunning = noteScheduleRunning.value;
    noteScheduleRunning.value = Boolean(state?.running);
    // It finished while we were watching: pick up what it wrote.
    if (wasRunning && !noteScheduleRunning.value) await loadBrief(briefDate.value || null);
  } catch {
    noteScheduleRunning.value = false;
  }
}

function startNoteSchedulePolling() {
  if (noteSchedulePoll) return;
  pollNoteSchedule();
  noteSchedulePoll = window.setInterval(pollNoteSchedule, 10000);
}

function stopNoteSchedulePolling() {
  if (!noteSchedulePoll) return;
  window.clearInterval(noteSchedulePoll);
  noteSchedulePoll = null;
}

const noteSectionCount = computed(() => {
  const note = brief.value?.note;
  if (!note) return 0;
  const sections = pickArray(note, "sections");
  return Array.isArray(sections) ? sections.length : 0;
});
const ledger = ref([]);
let activeStream = null;
let streamIdleTimer = null;
let activeRefreshContext = null;

const quoteTickers = computed(() => pulseQuoteUniverse());
const { quotes } = useLiveQuotes(quoteTickers);

const summary = computed(() => {
  const data = payload.value?.summary || null;
  if (!data) return null;
  return data.schema_version === 2 ? data : null;
});
const prompt = computed(() => {
  if (viewLang.value === "zh") {
    return summary.value?.research_prompt_zh || payload.value?.prompt_zh || "";
  }
  return (
    summary.value?.research_prompt_en ||
    summary.value?.research_prompt ||
    payload.value?.prompt_en ||
    payload.value?.prompt ||
    ""
  );
});
const stocks = computed(() => summary.value?.stocks || []);
const sourceList = computed(() => summary.value?.sources || []);
const draftCandidates = computed(() => refreshDraft.value?.candidates || []);
const draftStocks = computed(() => refreshDraft.value?.stocks || []);
const draftErrors = computed(() => refreshDraft.value?.errors || []);
const draftTotal = computed(
  () =>
    refreshDraft.value?.total_count ||
    draftCandidates.value.length ||
    draftStocks.value.length,
);
const sectorMax = computed(() =>
  Math.max(1, ...(summary.value?.sector_mix || []).map((s) => s.count || 0)),
);
const weekLabel = computed(() => pick(summary.value, "week_label"));
const marketPulse = computed(() => pick(summary.value, "market_pulse"));
const benchmarkContext = computed(() => pick(summary.value, "benchmark_context"));

const indexCards = computed(() => indexQuoteCards(quotes.value, PULSE_INDEX_TICKERS));
const sectorRows = computed(() => sectorRotationRows(quotes.value));
const macroRows = computed(() => macroTapeRows(quotes.value));
const breadth = computed(() => marketBreadthFromUniverse(screeners.value.universe || []));
const movers = computed(() => screenerMoverLists(screeners.value, 10));
const spyChange = computed(() => {
  const change = Number(quotes.value?.SPY?.change_pct_1d);
  return Number.isFinite(change) ? change : null;
});
const posture = computed(() => postureFromBreadth(breadth.value, spyChange.value));
const weekCalendar = computed(() => calendarWeekBuckets(calendar.value?.events || []));
const signalRows = computed(() => rankedSignalSlice(signalsPayload.value, 10));
const changedSince = computed(() => changedSinceSlice(signalsPayload.value));
const regime = computed(() => signalsPayload.value?.sections?.market_regime || {});
const ledgerStats = computed(() => ledgerHitStats(ledger.value));

watch(appLanguage, (lang) => {
  viewLang.value = lang;
});

function pick(obj, base) {
  if (!obj) return "";
  const en = obj[`${base}_en`];
  const zh = obj[`${base}_zh`];
  const fallback = obj[base];
  const order = viewLang.value === "zh" ? [zh, en, fallback] : [en, fallback, zh];
  for (const value of order) {
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

function pickArray(obj, base) {
  if (!obj) return [];
  const en = obj[`${base}_en`];
  const zh = obj[`${base}_zh`];
  const fallback = obj[base];
  const order = viewLang.value === "zh" ? [zh, en, fallback] : [en, fallback, zh];
  for (const value of order) {
    if (Array.isArray(value) && value.length) return value;
  }
  return [];
}

async function loadSummary() {
  loading.value = true;
  error.value = null;
  try {
    payload.value = await api.weeklyStocks.get();
    refreshDraft.value = payload.value?.draft || null;
    applyRefreshState(payload.value?.refresh_state);
  } catch (e) {
    error.value = e?.message || t("pulse.load_error");
  } finally {
    loading.value = false;
  }
}

async function loadMarketDesk() {
  marketLoading.value = true;
  try {
    const [screenerPayload, signalPayload] = await Promise.all([
      api.quoteScreeners().catch(() => ({ gainers: [], losers: [], active: [], universe: [] })),
      api.researchPages.marketPulse().catch(() => null),
    ]);
    screeners.value = screenerPayload || { gainers: [], losers: [], active: [], universe: [] };
    signalsPayload.value = signalPayload;
    const hot = [
      ...pulseQuoteUniverse().slice(0, 24),
      ...(stocks.value || []).map((row) => row.ticker),
      ...(screenerPayload?.gainers || []).slice(0, 8).map((row) => row.ticker),
      ...(screenerPayload?.losers || []).slice(0, 8).map((row) => row.ticker),
    ].filter(Boolean);
    calendar.value = await api.quoteCalendar(hot).catch(() => ({ events: [] }));
  } finally {
    marketLoading.value = false;
  }
}

function applyRefreshState(state) {
  if (!state || state.terminal_type !== "error") return;
  const lastEventAt = Date.parse(state.last_event_at || state.started_at || "");
  if (Number.isNaN(lastEventAt)) return;
  if (Date.now() - lastEventAt > 30 * 60 * 1000) return;
  const generatedAt = Date.parse(summary.value?.generated_at || "");
  if (!Number.isNaN(generatedAt) && generatedAt >= lastEventAt - 2000) return;
  error.value = `${t("pulse.last_failed")}: ${state.error || t("pulse.failed")}`;
}

async function initializeWeeklySummary() {
  await Promise.all([loadSummary(), loadMarketDesk(), loadBrief(), loadLedger()]);
  await attachActiveWeeklyRefresh();
  startNoteSchedulePolling();
}

async function loadBrief(date = null) {
  briefError.value = "";
  try {
    const [archive, latest] = await Promise.all([
      api.marketBriefArchive().catch(() => ({ dates: [] })),
      api.marketBrief(date).catch(() => null),
    ]);
    briefDates.value = archive?.dates || [];
    brief.value = latest;
    briefDate.value = latest?.date || "";
  } catch {
    briefDates.value = [];
    brief.value = null;
  }
}

async function runBrief() {
  if (briefRunning.value) return;
  briefRunning.value = true;
  briefError.value = "";
  try {
    brief.value = await api.runMarketBrief();
    briefDate.value = brief.value?.date || "";
    const archive = await api.marketBriefArchive().catch(() => null);
    if (archive?.dates) briefDates.value = archive.dates;
  } catch (e) {
    briefError.value = e?.message || t("pulse.brief_run_error");
  } finally {
    briefRunning.value = false;
  }
}

async function writeBriefNote() {
  if (noteWriting.value || !brief.value) return;
  noteWriting.value = true;
  briefError.value = "";
  try {
    brief.value = await api.writeMarketBriefNote(brief.value.date, noteLength.value);
  } catch (e) {
    briefError.value = e?.message || t("pulse.note_error");
  } finally {
    noteWriting.value = false;
  }
}

async function selectBriefDate(date) {
  if (!date || date === brief.value?.date) return;
  try {
    brief.value = await api.marketBrief(date);
    briefDate.value = date;
  } catch {
    briefError.value = t("pulse.brief_load_error");
  }
}

async function loadLedger() {
  try {
    const payload = await api.signalLedger();
    ledger.value = payload?.entries || [];
  } catch {
    ledger.value = [];
  }
}

async function dropLedgerEntry(id) {
  try {
    await api.deleteSignal(id);
  } catch {
    return;
  }
  await loadLedger();
}

async function attachActiveWeeklyRefresh() {
  if (refreshing.value) return;
  let jobs = [];
  try {
    jobs = await api.listActiveJobs();
  } catch {
    return;
  }
  const job = jobs.find(
    (item) =>
      item?.kind === "weekly_stocks" ||
      item?.stream_url === "/api/weekly-stocks/refresh/stream",
  );
  if (!job) return;
  const startedAtMs = Date.parse(job.started_at || "");
  const context = {
    startedAtMs: Number.isNaN(startedAtMs) ? Date.now() : startedAtMs,
    previousFingerprint: summaryFingerprint(summary.value),
    settled: false,
  };
  activeRefreshContext = context;
  refreshing.value = true;
  error.value = null;
  liveStatus.value = activeJobStatus(job);
  openStream(context);
}

function activeJobStatus(job) {
  if (job?.latest_stage) return job.latest_stage;
  const action = job?.latest_action || {};
  if (action.action === "tool_use" && action.tool) {
    return `${action.tool}: ${(action.preview || "").slice(0, 90)}`;
  }
  if (action.preview) return String(action.preview).slice(0, 90);
  return t("pulse.waiting_status");
}

async function refreshSummary({ force = false } = {}) {
  if (refreshing.value) return;
  const context = {
    startedAtMs: Date.now(),
    previousFingerprint: summaryFingerprint(summary.value),
    settled: false,
  };
  refreshDraft.value = {
    status: "running",
    phase: "starting",
    candidates: [],
    stocks: [],
    errors: [],
  };
  activeRefreshContext = context;
  refreshing.value = true;
  error.value = null;
  liveStatus.value = t("pulse.start_status");
  try {
    await api.weeklyStocks.refresh({ force });
    openStream(context);
  } catch (e) {
    activeRefreshContext = null;
    refreshing.value = false;
    liveStatus.value = "";
    error.value = e?.message || t("pulse.start_error");
  }
}

function openStream(context) {
  closeStream();
  const es = new EventSource(api.weeklyStocks.streamUrl());
  activeStream = es;
  armStreamIdleTimer(context);
  es.onmessage = async (ev) => {
    if (context.settled || activeRefreshContext !== context) return;
    armStreamIdleTimer(context);
    let entry;
    try {
      entry = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (!isFreshEvent(entry, context)) {
      if (entry.type === "done" || entry.type === "error") {
        liveStatus.value = t("pulse.waiting_status");
      }
      return;
    }
    if (applyDraftEvent(entry)) {
      return;
    } else if (entry.type === "stage" && entry.message) {
      liveStatus.value = entry.message;
    } else if (entry.type === "claude_action" && entry.action === "tool_use") {
      liveStatus.value = `${entry.tool}: ${(entry.preview || "").slice(0, 90)}`;
    } else if (entry.type === "claude_action" && entry.action === "thinking") {
      liveStatus.value = (entry.text || "").slice(0, 90);
    } else if (entry.type === "done") {
      if (entry.summary) {
        settleRefresh(context);
        payload.value = {
          ...(payload.value || {}),
          summary: entry.summary,
        };
        loadMarketDesk();
      } else {
        await finishRefreshFromPolling(context);
      }
    } else if (entry.type === "error") {
      settleRefresh(context, entry.error || t("pulse.failed"));
    }
  };
  es.onerror = async () => {
    if (activeStream !== es || !refreshing.value || context.settled) return;
    liveStatus.value = t("pulse.stream_stalled");
    await finishRefreshFromPolling(context);
  };
}

function applyDraftEvent(entry) {
  if (entry.type === "candidates") {
    refreshDraft.value = {
      ...(refreshDraft.value || {}),
      status: "running",
      phase: "details",
      candidates: entry.candidates || [],
      stocks: [],
      errors: [],
      total_count: entry.total_count || (entry.candidates || []).length,
    };
    liveStatus.value = entry.message || t("pulse.candidates");
    return true;
  }
  if (entry.type === "stock_started") {
    refreshDraft.value = {
      ...(refreshDraft.value || {}),
      status: "running",
      phase: "details",
      active_ticker: entry.ticker,
      index: entry.index,
      total_count: entry.total_count || draftTotal.value,
    };
    liveStatus.value = `${t("pulse.building")} ${entry.ticker || ""}`.trim();
    return true;
  }
  if (entry.type === "stock_done") {
    const current = refreshDraft.value || {};
    const nextStocks = upsertByTicker(current.stocks || [], entry.stock);
    refreshDraft.value = {
      ...current,
      status: "running",
      phase: "details",
      active_ticker: null,
      stocks: nextStocks,
      completed_count: entry.completed_count || nextStocks.length,
      index: entry.index,
      total_count: entry.total_count || current.total_count || nextStocks.length,
    };
    liveStatus.value = entry.message || `${t("pulse.completed")} ${entry.ticker || ""}`.trim();
    return true;
  }
  if (entry.type === "stock_error") {
    const current = refreshDraft.value || {};
    refreshDraft.value = {
      ...current,
      status: "running",
      phase: "details",
      active_ticker: null,
      errors: [
        ...(current.errors || []),
        {
          ticker: entry.ticker,
          error: entry.error,
        },
      ],
      index: entry.index,
      total_count: entry.total_count || current.total_count,
    };
    liveStatus.value = entry.message || `${t("pulse.skipped")} ${entry.ticker || ""}`.trim();
    return true;
  }
  if (entry.type === "publish_done") {
    refreshDraft.value = {
      ...(refreshDraft.value || {}),
      status: "complete",
      phase: "published",
      completed_count: entry.completed_count,
      skipped_count: entry.skipped_count,
      summary_generated_at: entry.generated_at,
    };
    liveStatus.value = entry.message || t("pulse.published");
    return true;
  }
  return false;
}

function upsertByTicker(items, nextItem) {
  if (!nextItem || !nextItem.ticker) return items || [];
  const ticker = String(nextItem.ticker).toUpperCase();
  const out = [];
  let found = false;
  for (const item of items || []) {
    if (String(item?.ticker || "").toUpperCase() === ticker) {
      out.push(nextItem);
      found = true;
    } else {
      out.push(item);
    }
  }
  if (!found) out.push(nextItem);
  return out;
}

function closeStream() {
  if (streamIdleTimer) {
    window.clearTimeout(streamIdleTimer);
    streamIdleTimer = null;
  }
  if (activeStream) {
    try {
      activeStream.close();
    } catch {
      // ignore close failures
    }
    activeStream = null;
  }
}

function armStreamIdleTimer(context) {
  if (streamIdleTimer) window.clearTimeout(streamIdleTimer);
  streamIdleTimer = window.setTimeout(() => {
    if (context?.settled) return;
    liveStatus.value = t("pulse.stream_stalled");
    finishRefreshFromPolling(context);
  }, 120000);
}

function settleRefresh(context, message = "") {
  if (context) {
    context.settled = true;
  }
  if (!context || activeRefreshContext === context) {
    activeRefreshContext = null;
  }
  closeStream();
  refreshing.value = false;
  liveStatus.value = "";
  error.value = message || null;
}

async function finishRefreshFromPolling(context) {
  if (!context || context.settled || activeRefreshContext !== context) return;
  closeStream();
  liveStatus.value = t("pulse.waiting_status");
  try {
    const updated = await waitForUpdatedSummary(context);
    if (context.settled || activeRefreshContext !== context) return;
    payload.value = updated;
    settleRefresh(context);
    loadMarketDesk();
  } catch (e) {
    if (context.settled || activeRefreshContext !== context) return;
    settleRefresh(context, e?.message || t("pulse.no_change"));
  }
}

async function waitForUpdatedSummary(context) {
  const deadline = Date.now() + 15 * 60 * 1000;
  let latest = null;
  while (Date.now() < deadline && !context.settled) {
    latest = await api.weeklyStocks.get();
    if (summaryIsFresh(latest?.summary, context)) {
      return latest;
    }
    await sleep(3000);
  }
  throw new Error(t("pulse.no_change"));
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isFreshEvent(entry, context) {
  const ts = Date.parse(entry?.ts || "");
  if (Number.isNaN(ts)) return true;
  return ts >= context.startedAtMs - 2000;
}

function summaryIsFresh(nextSummary, context) {
  if (!nextSummary) return false;
  const generatedAt = Date.parse(nextSummary.generated_at || "");
  if (!Number.isNaN(generatedAt) && generatedAt >= context.startedAtMs - 2000) {
    return true;
  }
  if (!context.previousFingerprint) return true;
  return summaryFingerprint(nextSummary) !== context.previousFingerprint;
}

function summaryFingerprint(value) {
  if (!value) return "";
  return [
    value.generated_at || "",
    value.as_of || "",
    value.week_label || "",
    value.market_pulse || "",
    (value.stocks || [])
      .map((stock) => `${stock.rank}:${stock.ticker}:${stock.score}`)
      .join("|"),
    (value.watchlist || []).map((item) => item.ticker).join("|"),
  ].join("||");
}

function fmtPct(value) {
  if (value == null || Number.isNaN(Number(value))) return t("pulse.na");
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${n.toFixed(Math.abs(n) >= 10 ? 0 : 1)}%`;
}

function fmtMultiple(value) {
  if (value == null || Number.isNaN(Number(value))) return t("pulse.na");
  return `${Number(value).toFixed(1)}x`;
}

function fmtUsd(value) {
  if (value == null || Number.isNaN(Number(value))) return t("pulse.na");
  const n = Number(value);
  if (n >= 1_000_000_000_000) return `$${(n / 1_000_000_000_000).toFixed(1)}T`;
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
}

function scoreTone(score, unverified = false) {
  if (unverified) return "text-ink-secondary";
  if (score >= 85) return "text-success-ink";
  if (score >= 70) return "text-warning-ink";
  return "text-ink-secondary";
}

function changeClass(change) {
  if (!Number.isFinite(Number(change))) return "text-ink-muted";
  return Number(change) >= 0 ? "text-success-ink" : "text-danger-ink";
}

function quotePrice(ticker) {
  return lastPriceLabel(quotes.value?.[ticker] || null);
}

function quoteChange(ticker) {
  return signedChange(quotes.value?.[ticker] || null);
}

function openTicker(ticker) {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!symbol) return;
  router.push({ name: "market-radar", query: { ticker: symbol } });
}

function refreshedAtLabel(iso) {
  if (!iso) return t("pulse.not_generated");
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(viewLang.value === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function moverChange(row) {
  const change = Number(row?.change_pct_1d ?? row?.change);
  return Number.isFinite(change) ? change : null;
}

function moverLast(row) {
  const last = Number(row?.last_price ?? row?.last);
  return Number.isFinite(last) ? last : null;
}

onMounted(initializeWeeklySummary);
onBeforeUnmount(() => {
  if (activeRefreshContext) {
    activeRefreshContext.settled = true;
    activeRefreshContext = null;
  }
  closeStream();
  stopNoteSchedulePolling();
});
</script>

<template>
  <div class="page-wide">
    <header class="mb-6">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <span
              v-if="weekLabel"
              class="inline-flex items-center gap-1.5 text-[13px] font-semibold text-accent-ink"
            >
              <CalendarClock class="h-3.5 w-3.5" />
              {{ weekLabel }}
            </span>
            <span
              v-if="summary?.generated_at"
              class="text-footnote text-ink-muted"
            >
              · {{ t("pulse.updated") }} {{ refreshedAtLabel(summary.generated_at) }}
            </span>
          </div>
          <h1 ref="pageTitleEl" class="page-title mt-1">{{ t("pulse.title") }}</h1>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <RouterLink class="btn-bordered focus-ring" :to="{ name: 'market-radar' }">
            {{ t("pulse.open_market") }}
          </RouterLink>
          <RouterLink class="btn-bordered focus-ring" :to="{ name: 'research-page-market-pulse' }">
            {{ t("pulse.open_signals") }}
          </RouterLink>
          <button
            type="button"
            class="btn-bordered focus-ring"
            :aria-pressed="expandedPrompt"
            @click="expandedPrompt = !expandedPrompt"
          >
            {{ t("pulse.prompt") }}
          </button>
          <button
            type="button"
            class="btn-filled focus-ring"
            :disabled="refreshing"
            @click="refreshSummary({ force: true })"
          >
            <Loader2 v-if="refreshing" class="h-4 w-4 animate-spin" />
            <RefreshCw v-else class="h-4 w-4" />
            {{ t("pulse.refresh") }}
          </button>
        </div>
      </div>
      <p class="mt-3 max-w-4xl text-[15px] leading-relaxed text-ink-secondary">
        {{ marketPulse || t("pulse.subtitle") }}
      </p>
    </header>

    <div
      v-if="expandedPrompt && prompt"
      class="mb-4 news-grouped px-4 py-3"
    >
      <div class="mb-2 text-footnote font-semibold text-ink-muted">
        {{ t("pulse.prompt_title") }}
      </div>
      <pre class="max-h-72 overflow-auto whitespace-pre-wrap text-footnote leading-relaxed text-ink-secondary">{{ prompt }}</pre>
    </div>

    <div
      v-if="liveStatus"
      class="mb-3 flex items-center gap-2 news-grouped px-4 py-3 text-callout text-accent-ink"
    >
      <Loader2 class="h-4 w-4 animate-spin" />
      <span class="truncate">{{ liveStatus }}</span>
    </div>

    <div
      v-if="refreshing && refreshDraft"
      class="mb-3 news-grouped px-4 py-3"
    >
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="text-callout font-semibold text-ink-primary">{{ t("pulse.progress_title") }}</div>
        <div class="flex items-center gap-3 text-caption1 text-ink-muted">
          <span>{{ t("pulse.completed") }} {{ draftStocks.length }}/{{ draftTotal || "?" }}</span>
          <span v-if="draftErrors.length">{{ t("pulse.skipped") }} {{ draftErrors.length }}</span>
        </div>
      </div>
      <div v-if="draftCandidates.length" class="mt-2 flex flex-wrap gap-1.5">
        <button
          v-for="candidate in draftCandidates"
          :key="candidate.ticker"
          type="button"
          class="rounded-subbox border border-subtle px-2 py-0.5 font-mono text-caption1 text-ink-secondary focus-ring"
          @click="openTicker(candidate.ticker)"
        >
          {{ candidate.ticker }}
        </button>
      </div>
    </div>

    <p v-if="error" class="mb-3 news-grouped px-4 py-3 text-callout text-danger">{{ error }}</p>

    <div class="space-y-5">
        <section class="news-grouped px-4 py-3" :aria-label="t('pulse.posture_label')">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="text-footnote font-semibold text-ink-muted">
              {{ t("pulse.posture_label") }}
            </div>
            <span class="text-callout font-medium text-ink-primary">
              {{ t(`pulse.posture_${posture}`) }}
            </span>
          </div>
          <p class="mt-1 text-callout text-ink-secondary">
            {{
              regime.posture_summary ||
              benchmarkContext ||
              t("pulse.posture_fallback")
            }}
          </p>
          <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div class="rounded-subbox bg-fill-tertiary/60 px-2.5 py-2">
              <div class="text-caption1 text-ink-muted">{{ t("pulse.breadth_up") }}</div>
              <div class="font-display text-title3 tabular text-success-ink">{{ breadth.up || 0 }}</div>
            </div>
            <div class="rounded-subbox bg-fill-tertiary/60 px-2.5 py-2">
              <div class="text-caption1 text-ink-muted">{{ t("pulse.breadth_down") }}</div>
              <div class="font-display text-title3 tabular text-danger-ink">{{ breadth.down || 0 }}</div>
            </div>
            <div class="rounded-subbox bg-fill-tertiary/60 px-2.5 py-2">
              <div class="text-caption1 text-ink-muted">{{ t("pulse.breadth_pct_up") }}</div>
              <div class="font-display text-title3 tabular text-ink-primary">
                {{ breadth.pctUp == null ? t("pulse.na") : `${breadth.pctUp.toFixed(0)}%` }}
              </div>
            </div>
            <div class="rounded-subbox bg-fill-tertiary/60 px-2.5 py-2">
              <div class="text-caption1 text-ink-muted">{{ t("pulse.breadth_near_high") }}</div>
              <div class="font-display text-title3 tabular text-ink-primary">
                {{ breadth.pctNearHigh == null ? t("pulse.na") : `${breadth.pctNearHigh.toFixed(0)}%` }}
              </div>
            </div>
          </div>
        </section>

        <section
          id="pulse-morning-brief"
          class="news-grouped px-4 py-3"
          :aria-label="t('pulse.morning_brief_label')"
          data-testid="morning-brief"
        >
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div class="text-footnote font-semibold text-ink-muted">
              {{ t("pulse.morning_brief_label") }}
            </div>
            <div class="flex flex-wrap items-center gap-1">
              <select
                v-if="briefDates.length"
                class="yf-range-item focus-ring"
                :value="briefDate"
                @change="selectBriefDate($event.target.value)"
              >
                <option v-for="date in briefDates" :key="date" :value="date">{{ date }}</option>
              </select>
              <button
                type="button"
                class="yf-range-item focus-ring"
                :disabled="briefRunning"
                @click="runBrief"
              >
                <Loader2 v-if="briefRunning" class="h-3.5 w-3.5 animate-spin" />
                {{ briefRunning ? t("pulse.brief_building") : t("pulse.brief_run") }}
              </button>
              <select
                v-if="brief"
                v-model="noteLength"
                class="yf-range-item focus-ring"
                :aria-label="t('pulse.note_length_label')"
              >
                <option value="short">{{ t("pulse.note_len_short") }}</option>
                <option value="long">{{ t("pulse.note_len_long") }}</option>
              </select>
              <button
                v-if="brief"
                type="button"
                class="yf-range-item focus-ring"
                :disabled="noteWriting"
                @click="writeBriefNote"
              >
                <Loader2 v-if="noteWriting" class="h-3.5 w-3.5 animate-spin" />
                {{
                  noteWriting
                    ? t("pulse.note_writing")
                    : brief.note
                      ? t("pulse.note_rewrite")
                      : t("pulse.note_write")
                }}
              </button>
            </div>
          </div>
          <p v-if="briefError" class="text-callout text-danger">{{ briefError }}</p>
          <template v-else-if="brief">
            <p class="text-caption1 text-ink-muted">
              {{ t("pulse.brief_as_of", { when: (brief.generated_at && refreshedAtLabel(brief.generated_at)) || brief.date }) }}
            </p>
            <article
              v-if="noteBuilding"
              class="morning-brief mt-2.5"
              data-testid="brief-note-loading"
              aria-busy="true"
              :aria-label="t('pulse.note_building')"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="section-label">{{ t("pulse.note_label") }}</span>
                <span class="chip bg-accent/10 text-accent-ink">
                  <Loader2 class="mr-1 inline h-3 w-3 animate-spin" />
                  {{ t("pulse.note_building") }}
                </span>
              </div>
              <div class="morning-brief-skeleton-line mt-2.5 h-6 w-4/5 max-w-[36rem]"></div>
              <div class="morning-brief-skeleton-line mt-1.5 h-3.5 w-2/5 max-w-[18rem]"></div>
              <div class="morning-brief-sections mt-3.5">
                <section v-for="n in 4" :key="`note-skel-${n}`" class="morning-brief-section">
                  <div class="morning-brief-skeleton-line h-4 w-3/5"></div>
                  <div class="morning-brief-skeleton-line mt-2 h-3 w-full"></div>
                  <div class="morning-brief-skeleton-line mt-1.5 h-3 w-full"></div>
                  <div class="morning-brief-skeleton-line mt-1.5 h-3 w-11/12"></div>
                  <div class="morning-brief-skeleton-line mt-1.5 h-3 w-4/5"></div>
                </section>
              </div>
              <p class="morning-brief-foot">{{ t("pulse.note_building_hint") }}</p>
            </article>

            <article
              v-else-if="brief.note"
              class="morning-brief mt-2.5"
              data-testid="brief-note"
            >
              <header class="morning-brief-measure">
                <div class="flex items-center justify-between gap-2">
                  <span class="section-label">{{ t("pulse.note_label") }}</span>
                  <span class="chip bg-accent/10 text-accent-ink">
                    {{ t("pulse.note_ai_tag") }}
                  </span>
                </div>
                <h3 class="morning-brief-headline mt-1.5">
                  {{ pick(brief.note, "headline") }}
                </h3>
                <p class="mt-1 text-footnote text-ink-muted">
                  {{ t("pulse.brief_as_of", { when: (brief.note.generated_at && refreshedAtLabel(brief.note.generated_at)) || brief.date }) }}
                  <template v-if="noteSectionCount">
                    · {{ t("pulse.note_sections", { count: noteSectionCount }) }}
                  </template>
                </p>
              </header>

              <ul
                v-if="pickArray(brief.note, 'bullets').length"
                class="morning-brief-bullets morning-brief-measure"
              >
                <li v-for="(line, i) in pickArray(brief.note, 'bullets')" :key="`note-${i}`">
                  {{ line }}
                </li>
              </ul>

              <div
                v-if="pickArray(brief.note, 'sections').length"
                class="morning-brief-sections"
              >
                <section
                  v-for="(section, i) in pickArray(brief.note, 'sections')"
                  :key="`note-sec-${i}`"
                  class="morning-brief-section"
                >
                  <h4 class="morning-brief-section-title">{{ section.title }}</h4>
                  <p class="morning-brief-body">{{ section.body }}</p>
                </section>
              </div>

              <!-- A long note makes claims about the world, so it shows what
                   it read. No sources means it was written unresearched. -->
              <p
                v-if="brief.note.length === 'long'"
                class="morning-brief-foot morning-brief-measure"
                data-testid="brief-note-sources"
              >
                <template v-if="brief.note.researched && (brief.note.sources || []).length">
                  {{ t("pulse.note_researched", { count: brief.note.sources.length }) }}
                  <span
                    v-for="(src, i) in (brief.note.sources || []).slice(0, 4)"
                    :key="`note-src-${i}`"
                  >{{ i ? " · " : " " }}<a
                      :href="src.url"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="underline decoration-dotted hover:text-ink-secondary"
                    >{{ src.title }}</a></span>
                </template>
                <template v-else>{{ t("pulse.note_unresearched") }}</template>
              </p>
            </article>

            <div class="mt-2 flex flex-wrap gap-2">
              <button
                v-for="row in (brief.indices || []).slice(0, 6)"
                :key="`brief-ix-${row.ticker}`"
                type="button"
                class="rounded-subbox bg-fill-tertiary/60 px-2.5 py-1.5 text-left focus-ring"
                @click="openTicker(row.ticker)"
              >
                <span class="font-mono text-caption1 text-ink-muted">{{ row.ticker }}</span>
                <span
                  class="ml-2 text-callout tabular"
                  :class="changeClass(row.change_pct_1d)"
                >
                  {{ fmtPct(row.change_pct_1d) }}
                </span>
              </button>
            </div>
            <div
              v-if="(brief.movers?.gainers || []).length || (brief.movers?.losers || []).length"
              class="mt-3 grid gap-3 sm:grid-cols-2"
            >
              <div>
                <div class="text-caption1 text-ink-muted">{{ t("pulse.brief_gainers") }}</div>
                <div class="mt-1 space-y-0.5">
                  <button
                    v-for="row in (brief.movers?.gainers || []).slice(0, 4)"
                    :key="`bg-${row.ticker}`"
                    type="button"
                    class="flex w-full items-center justify-between gap-2 rounded-sm text-left focus-ring"
                    @click="openTicker(row.ticker)"
                  >
                    <span class="font-display text-footnote tabular">{{ row.ticker }}</span>
                    <span class="text-callout tabular text-success">{{ fmtPct(row.change_pct_1d) }}</span>
                  </button>
                </div>
              </div>
              <div>
                <div class="text-caption1 text-ink-muted">{{ t("pulse.brief_losers") }}</div>
                <div class="mt-1 space-y-0.5">
                  <button
                    v-for="row in (brief.movers?.losers || []).slice(0, 4)"
                    :key="`bl-${row.ticker}`"
                    type="button"
                    class="flex w-full items-center justify-between gap-2 rounded-sm text-left focus-ring"
                    @click="openTicker(row.ticker)"
                  >
                    <span class="font-display text-footnote tabular">{{ row.ticker }}</span>
                    <span class="text-callout tabular text-danger">{{ fmtPct(row.change_pct_1d) }}</span>
                  </button>
                </div>
              </div>
            </div>
            <p
              v-if="(brief.alerts_last_day || []).length"
              class="mt-2 text-caption1 text-ink-secondary"
            >
              {{ t("pulse.brief_alerts", { n: brief.alerts_last_day.length }) }}
            </p>
            <p
              v-if="(brief.calendar || []).length"
              class="text-caption1 text-ink-muted"
            >
              {{ t("pulse.brief_calendar", { n: brief.calendar.length }) }}
            </p>
          </template>
          <p v-else class="text-callout text-ink-muted">{{ t("pulse.brief_empty") }}</p>
        </section>

        <section :aria-label="t('pulse.indexes_label')">
          <div class="mb-2 text-footnote font-semibold text-ink-muted">
            {{ t("pulse.indexes_label") }}
          </div>
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
            <button
              v-for="card in indexCards"
              :key="card.ticker"
              type="button"
              class="news-grouped px-3 py-2 text-left focus-ring"
              @click="openTicker(card.ticker)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="truncate text-caption1 text-ink-muted">{{ card.label }}</span>
                <span class="shrink-0 font-mono text-caption1 text-ink-subtle">{{ card.ticker }}</span>
              </div>
              <div class="mt-1 flex items-baseline justify-between gap-2">
                <span class="font-display text-title3 tabular text-ink-primary">
                  {{ quotePrice(card.ticker) }}
                </span>
                <span class="text-callout tabular" :class="changeClass(card.change)">
                  {{ quoteChange(card.ticker) }}
                </span>
              </div>
            </button>
          </div>
        </section>

        <section class="news-grouped px-4 py-3" :aria-label="t('pulse.sectors_label')">
          <div class="mb-2 flex items-center justify-between gap-2">
            <div class="text-footnote font-semibold text-ink-muted">
              {{ t("pulse.sectors_label") }}
            </div>
            <span class="text-caption1 text-ink-muted">{{ t("pulse.sectors_hint") }}</span>
          </div>
          <div class="space-y-1.5">
            <button
              v-for="row in sectorRows"
              :key="row.ticker"
              type="button"
              class="grid w-full grid-cols-[minmax(8rem,14rem)_1fr_minmax(4rem,5rem)_minmax(4.5rem,6rem)] items-center gap-3 rounded-subbox px-2 py-1.5 text-left hover:bg-fill-tertiary/50 focus-ring"
              @click="openTicker(row.ticker)"
            >
              <span class="truncate text-callout text-ink-secondary">{{ row.label }}</span>
              <div class="h-1.5 overflow-hidden rounded-full bg-fill-tertiary">
                <div
                  class="h-full rounded-full"
                  :class="Number(row.change) >= 0 ? 'bg-success' : 'bg-danger'"
                  :style="{
                    width: `${Math.min(100, Math.abs(Number(row.change) || 0) * 18 + 8)}%`,
                  }"
                />
              </div>
              <span class="text-right font-mono text-caption1 text-ink-muted">{{ row.ticker }}</span>
              <span class="text-right text-callout tabular" :class="changeClass(row.change)">
                {{ fmtPct(row.change) }}
              </span>
            </button>
            <p v-if="!sectorRows.length" class="py-3 text-callout text-ink-muted">
              {{ marketLoading ? t("common.loading") : t("pulse.sectors_empty") }}
            </p>
          </div>
        </section>

        <section class="news-grouped px-4 py-3" :aria-label="t('pulse.macro_label')">
          <div class="mb-2 text-footnote font-semibold text-ink-muted">
            {{ t("pulse.macro_label") }}
          </div>
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5 xl:grid-cols-9">
            <button
              v-for="row in macroRows"
              :key="row.ticker"
              type="button"
              class="rounded-subbox bg-fill-tertiary/50 px-2.5 py-2 text-left focus-ring"
              @click="openTicker(row.ticker)"
            >
              <div class="truncate text-caption1 text-ink-muted">{{ row.label }}</div>
              <div class="mt-0.5 flex items-baseline justify-between gap-2">
                <span class="font-mono text-footnote text-ink-primary">{{ row.ticker }}</span>
                <span class="text-callout tabular" :class="changeClass(row.change)">
                  {{ fmtPct(row.change) }}
                </span>
              </div>
              <div class="mt-0.5 font-display text-callout tabular text-ink-primary">
                {{ quotePrice(row.ticker) }}
              </div>
            </button>
          </div>
        </section>

        <section :aria-label="t('pulse.movers_label')">
          <div class="mb-2 text-footnote font-semibold text-ink-muted">
            {{ t("pulse.movers_label") }}
          </div>
          <div class="grid gap-3 lg:grid-cols-3">
            <div
              v-for="bucket in [
                { id: 'gainers', label: t('pulse.gainers'), rows: movers.gainers, icon: TrendingUp },
                { id: 'losers', label: t('pulse.losers'), rows: movers.losers, icon: TrendingDown },
                { id: 'active', label: t('pulse.most_active'), rows: movers.active, icon: Activity },
              ]"
              :key="bucket.id"
              class="news-grouped overflow-hidden"
            >
              <div class="flex items-center gap-1.5 border-b border-subtle/70 px-3 py-2 text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
                <component :is="bucket.icon" class="h-3.5 w-3.5" />
                {{ bucket.label }}
              </div>
              <button
                v-for="row in bucket.rows"
                :key="bucket.id + row.ticker"
                type="button"
                class="flex w-full items-center justify-between gap-2 border-b border-subtle/40 px-3 py-2 text-left last:border-0 hover:bg-fill-tertiary/40 focus-ring"
                @click="openTicker(row.ticker)"
              >
                <span class="min-w-0">
                  <span class="block font-mono text-callout font-semibold text-ink-primary">{{ row.ticker }}</span>
                  <span class="block truncate text-caption1 text-ink-muted">{{ row.name || row.ticker }}</span>
                </span>
                <span class="shrink-0 text-right">
                  <span class="block tabular text-callout text-ink-primary">
                    {{ moverLast(row) == null ? "—" : moverLast(row).toFixed(2) }}
                  </span>
                  <span class="block tabular text-caption1" :class="changeClass(moverChange(row))">
                    {{ fmtPct(moverChange(row)) }}
                  </span>
                </span>
              </button>
              <p v-if="!bucket.rows.length" class="px-3 py-4 text-callout text-ink-muted">
                {{ marketLoading ? t("common.loading") : t("pulse.movers_empty") }}
              </p>
            </div>
          </div>
        </section>

        <section class="news-grouped px-4 py-3" :aria-label="t('pulse.calendar_label')">
          <div class="mb-2 flex items-center justify-between gap-2">
            <div class="text-footnote font-semibold text-ink-muted">
              {{ t("pulse.calendar_label") }}
            </div>
            <span class="text-caption1 text-ink-muted">{{ t("pulse.calendar_hint") }}</span>
          </div>
          <div class="yf-week-grid grid gap-2 sm:grid-cols-7">
            <div
              v-for="day in weekCalendar"
              :key="day.date"
              class="rounded-subbox border border-subtle/60 px-2 py-2"
            >
              <div class="text-caption1 font-medium text-ink-muted">{{ day.label }}</div>
              <ul class="mt-1 space-y-1">
                <li
                  v-for="event in day.events.slice(0, 4)"
                  :key="day.date + (event.ticker || event.title) + event.kind"
                  class="truncate text-caption1 text-ink-secondary"
                >
                  <button
                    v-if="event.ticker"
                    type="button"
                    class="font-mono text-ink-primary focus-ring"
                    @click="openTicker(event.ticker)"
                  >
                    {{ event.ticker }}
                  </button>
                  <span v-else>{{ event.title || event.kind }}</span>
                  <span class="text-ink-muted"> · {{ event.kind }}</span>
                </li>
              </ul>
              <p v-if="!day.events.length" class="mt-1 text-caption1 text-ink-subtle">—</p>
            </div>
          </div>
        </section>

        <section v-if="loading" class="flex items-center gap-2 py-6 text-callout text-ink-muted">
          <Loader2 class="h-4 w-4 animate-spin" />
          {{ t("pulse.loading") }}
        </section>

        <template v-else-if="summary">
          <div
            v-if="summary.scan_fallback"
            class="flex items-start gap-2 rounded-subbox border border-warning/40 bg-warning-soft px-3 py-2 text-callout text-warning-ink"
          >
            <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0" />
            <span>{{ t("pulse.scan_fallback") }}</span>
          </div>

          <section class="news-grouped px-4 py-3" :aria-label="t('pulse.brief_label')">
            <div class="mb-2 text-footnote font-semibold text-ink-muted">
              {{ t("pulse.brief_label") }}
            </div>
            <p class="text-callout leading-relaxed text-ink-secondary">
              {{ marketPulse }}
            </p>
            <p v-if="benchmarkContext" class="mt-2 text-callout leading-relaxed text-ink-muted">
              {{ benchmarkContext }}
            </p>
            <div
              v-if="summary.summary_cards?.length"
              class="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4"
            >
              <div
                v-for="card in summary.summary_cards"
                :key="pick(card, 'label')"
                class="rounded-subbox bg-fill-tertiary/50 px-2.5 py-2"
              >
                <div class="text-caption1 text-ink-muted">{{ pick(card, "label") }}</div>
                <div class="mt-0.5 text-callout font-semibold text-ink-primary">{{ card.value }}</div>
                <div class="mt-0.5 text-caption1 text-ink-muted">{{ pick(card, "note") }}</div>
              </div>
            </div>
          </section>

          <section class="news-grouped overflow-hidden" :aria-label="t('pulse.setups_label')">
            <div class="flex items-center justify-between gap-2 border-b border-subtle/70 px-4 py-2">
              <div class="text-footnote font-semibold text-ink-muted">
                {{ t("pulse.setups_label") }}
              </div>
              <span class="text-caption1 text-ink-muted">
                {{ t("pulse.setups_count", { n: stocks.length }) }}
              </span>
            </div>
            <div class="overflow-x-auto">
              <table class="yf-fin-table min-w-full text-left">
                <thead>
                  <tr class="text-caption1 uppercase tracking-[0.04em] text-ink-muted">
                    <th class="px-3 py-2">#</th>
                    <th class="px-3 py-2">{{ t("pulse.col_symbol") }}</th>
                    <th class="px-3 py-2">{{ t("pulse.col_1w") }}</th>
                    <th class="px-3 py-2">{{ t("pulse.col_rel_vol") }}</th>
                    <th class="px-3 py-2">{{ t("pulse.col_rs") }}</th>
                    <th class="px-3 py-2">{{ t("pulse.col_score") }}</th>
                    <th class="px-3 py-2">{{ t("pulse.col_thesis") }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="stock in stocks"
                    :key="stock.ticker"
                    class="border-t border-subtle/50 align-top hover:bg-fill-tertiary/30"
                  >
                    <td class="px-3 py-2 text-caption1 text-ink-muted">{{ stock.rank }}</td>
                    <td class="px-3 py-2">
                      <button
                        type="button"
                        class="font-mono font-semibold text-ink-primary focus-ring"
                        @click="openTicker(stock.ticker)"
                      >
                        {{ stock.ticker }}
                      </button>
                      <div class="max-w-[12rem] truncate text-caption1 text-ink-muted">
                        {{ stock.name }}
                      </div>
                      <div v-if="pick(stock, 'sector')" class="text-caption1 text-ink-subtle">
                        {{ pick(stock, "sector") }}
                      </div>
                    </td>
                    <td class="px-3 py-2 tabular" :class="changeClass(stock.weekly_change_pct)">
                      {{ fmtPct(stock.weekly_change_pct) }}
                    </td>
                    <td class="px-3 py-2 tabular text-ink-primary">{{ fmtMultiple(stock.relative_volume) }}</td>
                    <td class="px-3 py-2 tabular text-ink-primary">{{ fmtPct(stock.relative_strength_pct) }}</td>
                    <td class="px-3 py-2">
                      <span class="font-display tabular" :class="scoreTone(stock.score, stock.is_fallback || summary.scan_fallback)">
                        {{ Math.round(stock.score || 0) }}
                      </span>
                    </td>
                    <td class="px-3 py-2 text-callout text-ink-secondary">
                      <div>{{ pick(stock, "why_awesome") }}</div>
                      <div v-if="pick(stock, 'catalyst')" class="mt-1 text-caption1 text-ink-muted">
                        {{ pick(stock, "catalyst") }}
                      </div>
                      <div v-if="pick(stock, 'risk')" class="mt-1 text-caption1 text-warning-ink">
                        {{ pick(stock, "risk") }}
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="grid gap-4 lg:grid-cols-2">
            <div class="news-grouped px-4 py-3">
              <div class="mb-2 text-footnote font-semibold text-ink-muted">
                {{ t("pulse.watchlist") }}
              </div>
              <div class="divide-y divide-subtle/60">
                <button
                  v-for="item in summary.watchlist || []"
                  :key="item.ticker"
                  type="button"
                  class="flex w-full flex-col gap-0.5 py-2 text-left focus-ring"
                  @click="openTicker(item.ticker)"
                >
                  <span class="font-mono font-semibold text-ink-primary">{{ item.ticker }}
                    <span class="ml-1 font-sans font-normal text-ink-muted">{{ item.name }}</span>
                  </span>
                  <span class="text-callout text-ink-secondary">{{ pick(item, "reason") }}</span>
                </button>
                <p v-if="!(summary.watchlist || []).length" class="py-3 text-callout text-ink-muted">
                  {{ t("pulse.watchlist_empty") }}
                </p>
              </div>
            </div>
            <div class="news-grouped px-4 py-3">
              <div class="mb-2 text-footnote font-semibold text-ink-muted">
                {{ t("pulse.sources") }}
              </div>
              <div class="space-y-1">
                <a
                  v-for="source in sourceList"
                  :key="(source.label || '') + (source.url || '')"
                  :href="source.url || '#'"
                  target="_blank"
                  rel="noreferrer"
                  class="flex items-start gap-2 rounded-subbox px-1 py-1.5 text-callout text-ink-secondary hover:bg-fill-tertiary/40 focus-ring"
                >
                  <ExternalLink class="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" />
                  <span class="min-w-0">
                    <span class="block truncate">{{ pick(source, "label") }}</span>
                    <span v-if="source.date" class="block text-caption1 text-ink-muted">{{ source.date }}</span>
                  </span>
                </a>
              </div>
            </div>
          </section>

          <section
            v-if="summary.sector_mix?.length"
            class="news-grouped px-4 py-3"
            :aria-label="t('pulse.theme_heat')"
          >
            <div class="mb-2 text-footnote font-semibold text-ink-muted">
              {{ t("pulse.theme_heat") }}
            </div>
            <div class="space-y-2">
              <div v-for="sector in summary.sector_mix" :key="sector.sector" class="space-y-1">
                <div class="flex items-center justify-between gap-3 text-caption1">
                  <span class="truncate text-ink-secondary">{{ pick(sector, "sector") }}</span>
                  <span class="font-mono text-ink-muted">{{ sector.count }}</span>
                </div>
                <div class="h-1.5 rounded-full bg-fill-tertiary">
                  <div
                    class="h-1.5 rounded-full bg-accent"
                    :style="{ width: `${Math.max(8, (sector.count / sectorMax) * 100)}%` }"
                  />
                </div>
              </div>
            </div>
          </section>
        </template>

        <section
          v-else
          class="news-grouped px-6 py-8 text-center"
        >
          <PulseECGIcon :size="28" class="mx-auto text-accent" />
          <h2 class="mt-3 font-display text-title3 text-ink-primary">{{ t("pulse.empty_title") }}</h2>
          <p class="mx-auto mt-2 max-w-xl text-callout text-ink-secondary">{{ t("pulse.empty_body") }}</p>
          <button
            type="button"
            class="btn-filled mt-4 focus-ring"
            :disabled="refreshing"
            @click="refreshSummary()"
          >
            <RefreshCw class="h-4 w-4" />
            {{ t("pulse.refresh") }}
          </button>
        </section>

        <div class="grid gap-4 lg:grid-cols-2">
          <section class="news-grouped px-4 py-3" :aria-label="t('pulse.signals_label')">
            <div class="mb-2 flex items-center justify-between gap-2">
              <div class="text-footnote font-semibold text-ink-muted">
                {{ t("pulse.signals_label") }}
              </div>
              <RouterLink
                class="text-caption1 font-medium text-accent-ink focus-ring"
                :to="{ name: 'research-page-market-pulse' }"
              >
                {{ t("pulse.open_signals") }}
              </RouterLink>
            </div>
            <div class="grid gap-2 sm:grid-cols-2">
              <button
                v-for="signal in signalRows"
                :key="signal.id || signal.title || signal.ticker"
                type="button"
                class="rounded-subbox border border-subtle/60 px-2.5 py-2 text-left hover:bg-fill-tertiary/40 focus-ring"
                @click="signal.ticker ? openTicker(signal.ticker) : null"
              >
                <div class="flex items-start justify-between gap-2">
                  <span class="text-callout font-medium text-ink-primary">
                    {{ signal.title || signal.theme || signal.ticker || t("pulse.signal_untitled") }}
                  </span>
                  <span
                    v-if="signal.direction"
                    class="shrink-0 text-caption1 uppercase text-ink-muted"
                  >
                    {{ signal.direction }}
                  </span>
                </div>
                <p class="mt-1 line-clamp-2 text-caption1 text-ink-secondary">
                  {{ signal.summary || signal.rationale || signal.why || "" }}
                </p>
              </button>
            </div>
            <p v-if="!signalRows.length" class="py-3 text-callout text-ink-muted">
              {{ t("pulse.signals_empty") }}
            </p>
          </section>

          <section class="news-grouped px-4 py-3" :aria-label="t('pulse.wow_label')">
            <div class="mb-2 text-footnote font-semibold text-ink-muted">
              {{ t("pulse.wow_label") }}
            </div>
            <div class="grid grid-cols-3 gap-2 text-center">
              <div class="rounded-subbox bg-fill-tertiary/50 px-2 py-2">
                <div class="text-caption1 text-ink-muted">{{ t("pulse.wow_new") }}</div>
                <div class="font-display text-title3 tabular">
                  {{ (changedSince.added || changedSince.new || []).length || changedSince.added_count || 0 }}
                </div>
              </div>
              <div class="rounded-subbox bg-fill-tertiary/50 px-2 py-2">
                <div class="text-caption1 text-ink-muted">{{ t("pulse.wow_removed") }}</div>
                <div class="font-display text-title3 tabular">
                  {{ (changedSince.removed || []).length || changedSince.removed_count || 0 }}
                </div>
              </div>
              <div class="rounded-subbox bg-fill-tertiary/50 px-2 py-2">
                <div class="text-caption1 text-ink-muted">{{ t("pulse.wow_changed") }}</div>
                <div class="font-display text-title3 tabular">
                  {{ (changedSince.changed || changedSince.updated || []).length || changedSince.changed_count || 0 }}
                </div>
              </div>
            </div>
            <p class="mt-2 text-caption1 text-ink-muted">{{ t("pulse.wow_hint") }}</p>
          </section>
        </div>

        <section
          v-if="ledger.length || ledgerStats.total"
          class="news-grouped px-4 py-3"
          :aria-label="t('pulse.ledger_label')"
          data-testid="signal-ledger"
        >
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div class="text-footnote font-semibold text-ink-muted">
              {{ t("pulse.ledger_label") }}
            </div>
            <div class="flex flex-wrap gap-3 text-caption1 text-ink-muted">
              <span v-if="ledgerStats.hitRate != null">
                {{ t("pulse.ledger_hit_rate", { n: ledgerStats.hitRate.toFixed(0) }) }}
              </span>
              <span v-if="ledgerStats.avgScore != null">
                {{ t("pulse.ledger_avg_score", { n: signedChange(ledgerStats.avgScore) }) }}
              </span>
              <span>{{ t("pulse.ledger_count", { n: ledgerStats.total }) }}</span>
            </div>
          </div>
          <div class="space-y-1">
            <div
              v-for="row in ledger.slice(0, 8)"
              :key="row.id"
              class="flex flex-wrap items-center justify-between gap-2 rounded-subbox px-2 py-1.5 hover:bg-fill-tertiary/40"
            >
              <button
                type="button"
                class="min-w-0 flex-1 text-left focus-ring rounded-sm"
                @click="openTicker(row.ticker)"
              >
                <span class="font-display text-footnote tabular text-ink-primary">{{ row.ticker }}</span>
                <span class="ml-2 text-caption1 uppercase text-ink-muted">{{ row.direction }}</span>
                <span class="ml-2 text-caption1 text-ink-secondary">{{ row.label }}</span>
              </button>
              <span
                v-if="row.score_pct != null"
                class="mono-data text-caption1 tabular"
                :class="row.score_pct >= 0 ? 'text-success' : 'text-danger'"
              >
                {{ signedChange(row.score_pct) }}
              </span>
              <span v-else class="text-caption1 text-ink-subtle">{{ t("pulse.ledger_unscored") }}</span>
              <button
                type="button"
                class="text-caption1 text-ink-muted focus-ring rounded-sm px-1"
                @click="dropLedgerEntry(row.id)"
              >
                {{ t("pulse.ledger_drop") }}
              </button>
            </div>
          </div>
        </section>
    </div>
  </div>
</template>
