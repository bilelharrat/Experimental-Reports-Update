<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CalendarClock,
  ExternalLink,
  Flame,
  Gauge,
  Languages,
  Loader2,
  RefreshCw,
  TrendingUp,
} from "lucide-vue-next";
import { api } from "../api.js";
import { appLanguage } from "../state.js";

const UI = {
  en: {
    back: "Home",
    title: "Weekly Summary",
    fallbackPulse: "Refresh to research the hottest stocks for the current trading week.",
    prompt: "Prompt",
    promptTitle: "Weekly stock research prompt",
    refresh: "Refresh",
    loading: "Loading weekly summary…",
    emptyTitle: "No weekly summary yet",
    emptyBody: "Start a refresh to research the current week's hottest stocks and build the dashboard.",
    leadSetup: "Lead setup",
    weeklyMarketPulse: "Weekly market pulse",
    score: "Score",
    weeklyMove: "Weekly move",
    relativeVolume: "Relative volume",
    marketCap: "Market cap",
    dashboardPulse: "Dashboard pulse",
    sectorHeat: "Sector heat",
    heat: "Heat",
    oneWeek: "1W",
    relVol: "Rel vol",
    rs: "RS",
    watchlist: "Watchlist",
    sources: "Sources",
    notGenerated: "Not generated",
    na: "n/a",
    startStatus: "Starting weekly research",
    loadError: "Could not load weekly summary.",
    startError: "Could not start weekly research.",
    failed: "Weekly research failed.",
    streamStalled: "Weekly research stream stalled. Try refresh again.",
  },
  zh: {
    back: "首页",
    title: "每周摘要",
    fallbackPulse: "刷新后研究本周最热门的股票，并生成仪表盘。",
    prompt: "提示词",
    promptTitle: "每周热门股票研究提示词",
    refresh: "刷新",
    loading: "正在加载每周摘要…",
    emptyTitle: "暂无每周摘要",
    emptyBody: "点击刷新，研究本周最热门股票并生成仪表盘。",
    leadSetup: "核心机会",
    weeklyMarketPulse: "每周市场脉搏",
    score: "评分",
    weeklyMove: "周涨幅",
    relativeVolume: "相对成交量",
    marketCap: "市值",
    dashboardPulse: "仪表盘脉搏",
    sectorHeat: "板块热度",
    heat: "热度",
    oneWeek: "1周",
    relVol: "相对量",
    rs: "相对强度",
    watchlist: "观察名单",
    sources: "来源",
    notGenerated: "尚未生成",
    na: "无",
    startStatus: "正在启动每周研究",
    loadError: "无法加载每周摘要。",
    startError: "无法启动每周研究。",
    failed: "每周研究失败。",
    streamStalled: "每周研究进度流已中断。请再次刷新。",
  },
};

const loading = ref(true);
const refreshing = ref(false);
const error = ref(null);
const payload = ref(null);
const liveStatus = ref("");
const expandedPrompt = ref(false);
const viewLang = ref(appLanguage.value);
let activeStream = null;
let streamIdleTimer = null;

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
const leader = computed(() => stocks.value[0] || null);
const sectorMax = computed(() =>
  Math.max(1, ...(summary.value?.sector_mix || []).map((s) => s.count || 0)),
);
const ui = computed(() => UI[viewLang.value] || UI.en);
const weekLabel = computed(() => pick(summary.value, "week_label"));
const marketPulse = computed(() => pick(summary.value, "market_pulse"));
const benchmarkContext = computed(() => pick(summary.value, "benchmark_context"));

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
  } catch (e) {
    error.value = e?.message || ui.value.loadError;
  } finally {
    loading.value = false;
  }
}

async function refreshSummary({ force = false } = {}) {
  if (refreshing.value) return;
  refreshing.value = true;
  error.value = null;
  liveStatus.value = ui.value.startStatus;
  try {
    await api.weeklyStocks.refresh({ force });
    openStream();
  } catch (e) {
    refreshing.value = false;
    liveStatus.value = "";
    error.value = e?.message || ui.value.startError;
  }
}

function openStream() {
  closeStream();
  const es = new EventSource(api.weeklyStocks.streamUrl());
  activeStream = es;
  armStreamIdleTimer();
  es.onmessage = async (ev) => {
    armStreamIdleTimer();
    let entry;
    try {
      entry = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (entry.type === "stage" && entry.message) {
      liveStatus.value = entry.message;
    } else if (entry.type === "claude_action" && entry.action === "tool_use") {
      liveStatus.value = `${entry.tool}: ${(entry.preview || "").slice(0, 90)}`;
    } else if (entry.type === "claude_action" && entry.action === "thinking") {
      liveStatus.value = (entry.text || "").slice(0, 90);
    } else if (entry.type === "done") {
      closeStream();
      refreshing.value = false;
      liveStatus.value = "";
      if (entry.summary) {
        payload.value = {
          ...(payload.value || {}),
          summary: entry.summary,
        };
      } else {
        await loadSummary();
      }
    } else if (entry.type === "error") {
      closeStream();
      refreshing.value = false;
      liveStatus.value = "";
      error.value = entry.error || ui.value.failed;
    }
  };
  es.onerror = () => {
    if (activeStream !== es || !refreshing.value) return;
    stopRefreshingWithError(ui.value.streamStalled);
  };
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

function armStreamIdleTimer() {
  if (streamIdleTimer) window.clearTimeout(streamIdleTimer);
  streamIdleTimer = window.setTimeout(() => {
    stopRefreshingWithError(ui.value.streamStalled);
  }, 120000);
}

function stopRefreshingWithError(message) {
  closeStream();
  refreshing.value = false;
  liveStatus.value = "";
  error.value = message;
  loadSummary();
}

function fmtPct(value) {
  if (value == null || Number.isNaN(Number(value))) return ui.value.na;
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${n.toFixed(Math.abs(n) >= 10 ? 0 : 1)}%`;
}

function fmtMultiple(value) {
  if (value == null || Number.isNaN(Number(value))) return ui.value.na;
  return `${Number(value).toFixed(1)}x`;
}

function fmtUsd(value) {
  if (value == null || Number.isNaN(Number(value))) return ui.value.na;
  const n = Number(value);
  if (n >= 1_000_000_000_000) return `$${(n / 1_000_000_000_000).toFixed(1)}T`;
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
}

function scoreTone(score) {
  if (score >= 85) return "text-success-ink";
  if (score >= 70) return "text-warning-ink";
  return "text-ink-secondary";
}

function scoreRing(score) {
  const clamped = Math.max(0, Math.min(100, Number(score) || 0));
  return {
    background: `conic-gradient(rgb(var(--color-success)) ${clamped * 3.6}deg, rgb(var(--color-surface-muted)) 0deg)`,
  };
}

function sparklinePoints(points) {
  if (!Array.isArray(points) || points.length < 2) return "";
  return points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * 100;
      const y = 48 - (Math.max(0, Math.min(100, Number(p.value) || 0)) / 100) * 42;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function refreshedAtLabel(iso) {
  if (!iso) return ui.value.notGenerated;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(viewLang.value === "zh" ? "zh-CN" : "en-US");
}

onMounted(loadSummary);
onBeforeUnmount(closeStream);
</script>

<template>
  <div class="max-w-7xl mx-auto px-6 lg:px-8 py-8">
    <header class="flex flex-col gap-4 border-b border-subtle pb-5 lg:flex-row lg:items-start lg:justify-between">
      <div class="min-w-0">
        <RouterLink
          to="/"
          class="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink-primary focus-ring rounded"
        >
          <ArrowLeft class="h-4 w-4" />
          {{ ui.back }}
        </RouterLink>
        <div class="mt-4 flex flex-wrap items-center gap-3">
          <h1 class="font-display text-2xl font-semibold text-ink-primary">
            {{ ui.title }}
          </h1>
          <span
            v-if="weekLabel"
            class="inline-flex items-center gap-1.5 rounded-full border border-subtle bg-surface px-2.5 py-1 text-xs text-ink-secondary"
          >
            <CalendarClock class="h-3.5 w-3.5" />
            {{ weekLabel }}
          </span>
        </div>
        <p class="mt-2 max-w-3xl text-sm text-ink-secondary">
          {{ marketPulse || ui.fallbackPulse }}
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <div
          class="inline-flex overflow-hidden rounded-lg border border-subtle bg-surface text-sm shadow-card"
          role="group"
          aria-label="Weekly summary language"
        >
          <button
            type="button"
            @click="viewLang = 'en'"
            :class="[
              'inline-flex items-center gap-1.5 px-3 py-2 focus-ring',
              viewLang === 'en'
                ? 'bg-accent text-white'
                : 'text-ink-secondary hover:bg-surface-muted',
            ]"
            :aria-pressed="viewLang === 'en'"
          >
            <Languages v-if="viewLang === 'en'" class="h-3.5 w-3.5" />
            EN
          </button>
          <button
            type="button"
            @click="viewLang = 'zh'"
            :class="[
              'inline-flex items-center gap-1.5 border-l border-subtle px-3 py-2 focus-ring',
              viewLang === 'zh'
                ? 'bg-accent text-white'
                : 'text-ink-secondary hover:bg-surface-muted',
            ]"
            :aria-pressed="viewLang === 'zh'"
          >
            <Languages v-if="viewLang === 'zh'" class="h-3.5 w-3.5" />
            中
          </button>
        </div>
        <button
          type="button"
          @click="expandedPrompt = !expandedPrompt"
          class="inline-flex items-center gap-2 rounded-lg border border-subtle bg-surface px-3 py-2 text-sm font-medium text-ink-secondary hover:bg-surface-muted focus-ring"
        >
          <BarChart3 class="h-4 w-4" />
          {{ ui.prompt }}
        </button>
        <button
          type="button"
          @click="refreshSummary({ force: true })"
          :disabled="refreshing"
          class="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-60 focus-ring"
        >
          <Loader2 v-if="refreshing" class="h-4 w-4 animate-spin" />
          <RefreshCw v-else class="h-4 w-4" />
          {{ ui.refresh }}
        </button>
      </div>
    </header>

    <div
      v-if="expandedPrompt"
      class="mt-5 rounded-card border border-subtle bg-surface shadow-card"
    >
      <div class="border-b border-subtle px-4 py-3 text-sm font-semibold text-ink-primary">
        {{ ui.promptTitle }}
      </div>
      <pre class="max-h-80 overflow-auto whitespace-pre-wrap px-4 py-3 text-xs leading-relaxed text-ink-secondary">{{ prompt }}</pre>
    </div>

    <div
      v-if="liveStatus"
      class="mt-5 flex items-center gap-2 rounded-card border border-accent/30 bg-accent-soft px-4 py-3 text-sm text-accent-ink"
    >
      <Loader2 class="h-4 w-4 animate-spin" />
      <span class="truncate">{{ liveStatus }}</span>
    </div>

    <div v-if="error" class="mt-5 rounded-card border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger-ink">
      {{ error }}
    </div>

    <div v-if="loading" class="mt-10 flex items-center gap-2 text-sm text-ink-muted">
      <Loader2 class="h-4 w-4 animate-spin" />
      {{ ui.loading }}
    </div>

    <div
      v-else-if="!summary"
      class="mt-10 rounded-card border border-subtle bg-surface px-6 py-8 text-center shadow-card"
    >
      <Flame class="mx-auto h-8 w-8 text-accent" />
      <h2 class="mt-3 font-display text-lg font-semibold text-ink-primary">
        {{ ui.emptyTitle }}
      </h2>
      <p class="mx-auto mt-2 max-w-xl text-sm text-ink-secondary">
        {{ ui.emptyBody }}
      </p>
      <button
        type="button"
        @click="refreshSummary()"
        :disabled="refreshing"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-60 focus-ring"
      >
        <Loader2 v-if="refreshing" class="h-4 w-4 animate-spin" />
        <RefreshCw v-else class="h-4 w-4" />
        {{ ui.refresh }}
      </button>
    </div>

    <template v-else>
      <section class="mt-6 grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div class="rounded-card border border-subtle bg-surface p-5 shadow-card">
          <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
              <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <Flame class="h-3.5 w-3.5" />
                {{ ui.leadSetup }}
              </div>
              <h2 class="mt-3 font-display text-2xl font-semibold text-ink-primary">
                <span v-if="leader">{{ leader.ticker }} · {{ leader.name }}</span>
                <span v-else>{{ ui.weeklyMarketPulse }}</span>
              </h2>
              <p class="mt-2 text-sm leading-6 text-ink-secondary">
                {{ pick(leader, "why_awesome") || benchmarkContext }}
              </p>
            </div>
            <div
              v-if="leader"
              class="grid h-20 w-20 shrink-0 place-items-center rounded-full p-1"
              :style="scoreRing(leader.score)"
            >
              <div class="grid h-full w-full place-items-center rounded-full bg-surface text-center">
                <div>
                  <div class="font-display text-xl font-semibold" :class="scoreTone(leader.score)">
                    {{ Math.round(leader.score) }}
                  </div>
                  <div class="text-[10px] uppercase text-ink-muted">{{ ui.score }}</div>
                </div>
              </div>
            </div>
          </div>
          <div class="mt-5 grid gap-3 border-t border-subtle pt-4 sm:grid-cols-3">
            <div>
              <div class="text-xs text-ink-muted">{{ ui.weeklyMove }}</div>
              <div class="mt-1 text-lg font-semibold text-success-ink">
                {{ fmtPct(leader?.weekly_change_pct) }}
              </div>
            </div>
            <div>
              <div class="text-xs text-ink-muted">{{ ui.relativeVolume }}</div>
              <div class="mt-1 text-lg font-semibold text-ink-primary">
                {{ fmtMultiple(leader?.relative_volume) }}
              </div>
            </div>
            <div>
              <div class="text-xs text-ink-muted">{{ ui.marketCap }}</div>
              <div class="mt-1 text-lg font-semibold text-ink-primary">
                {{ fmtUsd(leader?.market_cap_usd) }}
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-card border border-subtle bg-surface p-5 shadow-card">
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm font-semibold text-ink-primary">{{ ui.dashboardPulse }}</div>
            <span class="text-xs text-ink-muted">{{ refreshedAtLabel(summary.generated_at || summary.as_of) }}</span>
          </div>
          <div class="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-subtle pt-4">
            <div
              v-for="card in summary.summary_cards"
              :key="card.label + card.label_zh"
              class="min-w-0"
            >
              <div class="text-xs text-ink-muted">{{ pick(card, "label") }}</div>
              <div class="mt-1 text-base font-semibold text-ink-primary">{{ card.value }}</div>
              <div class="mt-1 text-[11px] leading-snug text-ink-muted">{{ pick(card, "note") }}</div>
            </div>
          </div>
        </div>
      </section>

      <section class="mt-6 grid gap-4 lg:grid-cols-[1fr_2fr]">
        <div class="rounded-card border border-subtle bg-surface p-5 shadow-card">
          <div class="flex items-center gap-2 text-sm font-semibold text-ink-primary">
            <Activity class="h-4 w-4 text-accent" />
            {{ ui.sectorHeat }}
          </div>
          <div class="mt-4 space-y-3">
            <div
              v-for="sector in summary.sector_mix"
              :key="sector.sector"
              class="space-y-1"
            >
              <div class="flex items-center justify-between gap-3 text-xs">
                <span class="truncate text-ink-secondary">{{ pick(sector, "sector") }}</span>
                <span class="font-mono text-ink-muted">{{ sector.count }}</span>
              </div>
              <div class="h-2 rounded-full bg-surface-muted">
                <div
                  class="h-2 rounded-full bg-accent"
                  :style="{ width: `${Math.max(8, (sector.count / sectorMax) * 100)}%` }"
                ></div>
              </div>
            </div>
          </div>
          <div class="mt-5 border-t border-subtle pt-4 text-xs leading-5 text-ink-secondary">
            {{ benchmarkContext }}
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <article
            v-for="stock in stocks"
            :key="stock.ticker"
            class="rounded-card border border-subtle bg-surface p-4 shadow-card"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[11px] text-ink-muted">#{{ stock.rank }}</span>
                  <h3 class="font-display text-lg font-semibold text-ink-primary">
                    {{ stock.ticker }}
                  </h3>
                  <span class="truncate text-sm text-ink-muted">{{ stock.name }}</span>
                </div>
                <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-muted">
                  <span v-if="stock.exchange">{{ stock.exchange }}</span>
                  <span v-if="pick(stock, 'sector')">· {{ pick(stock, "sector") }}</span>
                  <span>· {{ fmtUsd(stock.market_cap_usd) }}</span>
                </div>
              </div>
              <div class="text-right">
                <div class="font-display text-xl font-semibold" :class="scoreTone(stock.score)">
                  {{ Math.round(stock.score) }}
                </div>
                <div class="text-[10px] uppercase text-ink-muted">{{ ui.heat }}</div>
              </div>
            </div>

            <div class="mt-4 h-16 rounded-lg border border-subtle bg-surface-muted px-2 py-2">
              <svg viewBox="0 0 100 52" preserveAspectRatio="none" class="h-full w-full">
                <polyline
                  :points="sparklinePoints(stock.sparkline)"
                  fill="none"
                  stroke="rgb(var(--color-accent))"
                  stroke-width="3"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  vector-effect="non-scaling-stroke"
                />
              </svg>
            </div>

            <div class="mt-4 grid grid-cols-3 gap-2 text-center">
              <div>
                <div class="text-xs text-ink-muted">{{ ui.oneWeek }}</div>
                <div class="text-sm font-semibold text-success-ink">{{ fmtPct(stock.weekly_change_pct) }}</div>
              </div>
              <div>
                <div class="text-xs text-ink-muted">{{ ui.relVol }}</div>
                <div class="text-sm font-semibold text-ink-primary">{{ fmtMultiple(stock.relative_volume) }}</div>
              </div>
              <div>
                <div class="text-xs text-ink-muted">{{ ui.rs }}</div>
                <div class="text-sm font-semibold text-ink-primary">{{ fmtPct(stock.relative_strength_pct) }}</div>
              </div>
            </div>

            <p class="mt-4 text-sm leading-5 text-ink-secondary">
              {{ pick(stock, "why_awesome") }}
            </p>

            <div class="mt-4 space-y-2">
              <div
                v-for="driver in stock.drivers"
                :key="driver.label"
                class="space-y-1"
              >
                <div class="flex items-center justify-between gap-3 text-xs">
                  <span class="font-medium text-ink-secondary">{{ pick(driver, "label") }}</span>
                  <span class="font-mono text-ink-muted">{{ driver.value }}</span>
                </div>
                <div class="h-1.5 rounded-full bg-surface-muted">
                  <div
                    class="h-1.5 rounded-full bg-success"
                    :style="{ width: `${Math.max(4, Math.min(100, driver.score || 0))}%` }"
                  ></div>
                </div>
              </div>
            </div>

            <div class="mt-4 grid gap-2 text-xs">
              <div class="flex items-start gap-2 text-ink-secondary">
                <TrendingUp class="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                <span>{{ pick(stock, "setup") }}</span>
              </div>
              <div v-if="pick(stock, 'catalyst')" class="flex items-start gap-2 text-ink-secondary">
                <Gauge class="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                <span>{{ pick(stock, "catalyst") }}</span>
              </div>
              <div v-if="pick(stock, 'risk')" class="flex items-start gap-2 text-ink-secondary">
                <AlertTriangle class="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                <span>{{ pick(stock, "risk") }}</span>
              </div>
            </div>

            <div class="mt-4 flex flex-wrap gap-1.5">
              <span
                v-for="tag in pickArray(stock, 'tags')"
                :key="tag"
                class="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] text-ink-secondary"
              >
                {{ tag }}
              </span>
            </div>
          </article>
        </div>
      </section>

      <section class="mt-6 grid gap-4 lg:grid-cols-2">
        <div class="rounded-card border border-subtle bg-surface p-5 shadow-card">
          <div class="text-sm font-semibold text-ink-primary">{{ ui.watchlist }}</div>
          <div class="mt-3 divide-y divide-subtle">
            <div
              v-for="item in summary.watchlist"
              :key="item.ticker"
              class="py-3 first:pt-0 last:pb-0"
            >
              <div class="flex items-center gap-2">
                <span class="font-mono text-sm font-semibold text-ink-primary">{{ item.ticker }}</span>
                <span class="text-sm text-ink-muted">{{ item.name }}</span>
              </div>
              <p class="mt-1 text-sm text-ink-secondary">{{ pick(item, "reason") }}</p>
            </div>
          </div>
        </div>

        <div class="rounded-card border border-subtle bg-surface p-5 shadow-card">
          <div class="text-sm font-semibold text-ink-primary">{{ ui.sources }}</div>
          <div class="mt-3 space-y-2">
            <a
              v-for="source in sourceList"
              :key="source.label + source.url"
              :href="source.url || '#'"
              target="_blank"
              rel="noreferrer"
              class="flex items-start gap-2 rounded-lg px-2 py-1.5 text-sm text-ink-secondary hover:bg-surface-muted focus-ring"
            >
              <ExternalLink class="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" />
              <span class="min-w-0 flex-1">
                <span class="block truncate">{{ pick(source, "label") }}</span>
                <span v-if="source.date" class="block text-xs text-ink-muted">{{ source.date }}</span>
              </span>
            </a>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
