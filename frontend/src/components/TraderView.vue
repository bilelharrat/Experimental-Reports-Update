<script setup>
// Top of the public-company company-detail page. Renders the six
// trader cards (price, momentum, sentiment, heat, catalysts, news)
// plus the "Refresh trader view" CTA that drives them.
//
// Spec: docs/public-company-trader-view.md.

import { computed, onBeforeUnmount, ref } from "vue";
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  Flame,
  Gauge,
  Loader2,
  Newspaper,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import {
  cardStaleness,
  changeBias,
  fmtCount,
  fmtPct,
  fmtPrice,
  relativeAge,
} from "../trader.js";

const t = useT();

const props = defineProps({
  company: { type: Object, required: true },
});
const emit = defineEmits(["refreshed"]);

const refreshing = ref(false);
const refreshError = ref(null);
const liveStatus = ref("");
let activeStream = null;

const snapshot = computed(() => props.company.trader_snapshot || null);
const refreshedAt = computed(() => snapshot.value?.refreshed_at || null);

function staleness(cardKey) {
  return cardStaleness(refreshedAt.value, cardKey);
}

function stalenessClass(bucket) {
  if (bucket === "fresh") return "bg-success-soft text-success-ink";
  if (bucket === "warn") return "bg-warning-soft text-warning-ink";
  if (bucket === "stale") return "bg-danger/10 text-danger";
  return "bg-surface-muted text-ink-muted";
}

function stalenessLabel(bucket) {
  if (bucket === "fresh") return t("trader.fresh");
  if (bucket === "warn") return t("trader.warn");
  if (bucket === "stale") return t("trader.stale");
  return "";
}

function changeClass(v) {
  const bias = changeBias(v);
  if (bias === "up") return "text-success-ink";
  if (bias === "down") return "text-danger";
  return "text-ink-muted";
}

async function onRefresh() {
  refreshing.value = true;
  refreshError.value = null;
  liveStatus.value = "";
  try {
    const job = await api.trader.refresh(props.company.id);
    openStream(job.stream_url);
  } catch (e) {
    refreshing.value = false;
    refreshError.value = e?.message || t("trader.refresh_failed");
  }
}

function openStream(streamUrl) {
  closeStream();
  // streamUrl from the API is relative; withApiToken in api.trader.streamUrl
  // already handles that — but `job.stream_url` is the raw `/api/...` form,
  // so wrap it through withApiToken via the dedicated helper.
  const url = api.trader.streamUrl(props.company.id);
  const es = new EventSource(url);
  activeStream = es;
  es.onmessage = async (ev) => {
    let entry;
    try { entry = JSON.parse(ev.data); } catch { return; }
    if (entry.type === "stage" && entry.message) {
      liveStatus.value = entry.message;
    } else if (entry.type === "claude_action" && entry.action === "tool_use") {
      liveStatus.value = `${entry.tool}: ${(entry.preview || "").slice(0, 80)}`;
    } else if (entry.type === "done") {
      closeStream();
      refreshing.value = false;
      liveStatus.value = "";
      // Pull the updated company record so trader_snapshot is fresh in
      // the parent. We let the parent overwrite its prop reference.
      try {
        const fresh = await api.getCompany(props.company.id);
        emit("refreshed", fresh);
      } catch {
        emit("refreshed", null);
      }
    } else if (entry.type === "error") {
      closeStream();
      refreshing.value = false;
      refreshError.value = entry.error || t("trader.refresh_failed");
    }
  };
  es.onerror = () => {
    // EventSource raises onerror both for transient hiccups and for
    // permanent connection failures. We only flip back to "not
    // refreshing" once the server has terminated the stream (done /
    // error). Otherwise the browser will reconnect.
  };
}

function closeStream() {
  if (activeStream) {
    try { activeStream.close(); } catch { /* */ }
    activeStream = null;
  }
}

onBeforeUnmount(closeStream);

// ---- Small per-card view models ----

const price = computed(() => snapshot.value?.price_card || null);
const momentum = computed(() => snapshot.value?.momentum_card || null);
const sentiment = computed(() => snapshot.value?.sentiment_card || null);
const heat = computed(() => snapshot.value?.heat_card || null);
const catalysts = computed(() => snapshot.value?.catalysts || []);
const traderNews = computed(() => snapshot.value?.trader_news || []);

function biasLabel(b) {
  if (b === "positive") return t("trader.bias.positive");
  if (b === "negative") return t("trader.bias.negative");
  if (b === "neutral") return t("trader.bias.neutral");
  return "";
}

function biasClass(b) {
  if (b === "positive") return "bg-success-soft text-success-ink";
  if (b === "negative") return "bg-danger/10 text-danger";
  return "bg-surface-muted text-ink-secondary";
}

function impactClass(impact) {
  if (impact === "high") return "bg-danger/10 text-danger";
  if (impact === "medium") return "bg-warning-soft text-warning-ink";
  return "bg-surface-muted text-ink-secondary";
}

function catalystTypeLabel(typ) {
  return t(`trader.catalysts.type_${typ || "other"}`);
}

function impactLabel(impact) {
  if (!impact) return "";
  return t(`trader.catalysts.impact_${impact}`);
}

function skewLabel(s) {
  if (s === "call_bid") return t("trader.heat.skew_call_bid");
  if (s === "balanced") return t("trader.heat.skew_balanced");
  if (s === "put_bid") return t("trader.heat.skew_put_bid");
  return "—";
}

function socialLabel(s) {
  if (s === "rising") return t("trader.heat.social_rising");
  if (s === "flat") return t("trader.heat.social_flat");
  if (s === "falling") return t("trader.heat.social_falling");
  return "—";
}
</script>

<template>
  <section class="mt-4 space-y-3">
    <!-- Header: refresh CTA + "updated X ago" caption + status banner. -->
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div class="flex items-center gap-2 text-xs text-ink-muted">
        <span class="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          {{ t("trader.card.price") }} · {{ t("trader.card.momentum") }} ·
          {{ t("trader.card.sentiment") }}
        </span>
        <span v-if="refreshedAt" class="text-ink-muted">
          · {{ t("trader.refreshed_at", { when: relativeAge(refreshedAt) }) }}
        </span>
      </div>
      <button
        type="button"
        @click="onRefresh"
        :disabled="refreshing"
        class="text-xs px-3 py-1.5 rounded border border-subtle hover:bg-surface-muted text-ink-primary focus-ring inline-flex items-center gap-1.5 disabled:opacity-60"
      >
        <Loader2 v-if="refreshing" class="h-3.5 w-3.5 animate-spin" />
        <RefreshCw v-else class="h-3.5 w-3.5" />
        <span>{{ refreshing ? t("trader.refreshing") : t("trader.refresh") }}</span>
      </button>
    </div>

    <div v-if="liveStatus" class="text-xs text-ink-muted italic">{{ liveStatus }}</div>
    <div v-if="refreshError" class="text-xs text-danger">{{ refreshError }}</div>

    <!-- Empty state: no snapshot yet. -->
    <div
      v-if="!snapshot"
      class="rounded-card border border-dashed border-subtle p-6 text-sm text-ink-secondary text-center"
    >
      {{ t("trader.never_refreshed") }}
    </div>

    <!-- Card grid -->
    <div v-else class="grid gap-3 md:grid-cols-3">
      <!-- Price -->
      <div class="bg-surface border border-subtle rounded-card p-4 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <Activity class="h-3.5 w-3.5" />
            {{ t("trader.card.price") }}
          </div>
          <span :class="['text-[10px] px-1.5 py-0.5 rounded', stalenessClass(staleness('price_card'))]">
            {{ stalenessLabel(staleness('price_card')) }}
          </span>
        </div>
        <div class="text-2xl font-display text-ink-primary">
          {{ fmtPrice(price?.last_price, price?.currency) }}
        </div>
        <div class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <div class="text-ink-muted">{{ t("trader.price.change_1d") }}</div>
          <div :class="['font-mono', changeClass(price?.change_pct_1d)]">{{ fmtPct(price?.change_pct_1d) }}</div>
          <div class="text-ink-muted">{{ t("trader.price.change_5d") }}</div>
          <div :class="['font-mono', changeClass(price?.change_pct_5d)]">{{ fmtPct(price?.change_pct_5d) }}</div>
          <div class="text-ink-muted">{{ t("trader.price.change_30d") }}</div>
          <div :class="['font-mono', changeClass(price?.change_pct_30d)]">{{ fmtPct(price?.change_pct_30d) }}</div>
          <div class="text-ink-muted">{{ t("trader.price.change_ytd") }}</div>
          <div :class="['font-mono', changeClass(price?.change_pct_ytd)]">{{ fmtPct(price?.change_pct_ytd) }}</div>
          <div class="text-ink-muted">{{ t("trader.price.change_1y") }}</div>
          <div :class="['font-mono', changeClass(price?.change_pct_1y)]">{{ fmtPct(price?.change_pct_1y) }}</div>
          <div class="text-ink-muted">{{ t("trader.price.vs_sector_30d") }}</div>
          <div :class="['font-mono', changeClass(price?.vs_sector_30d_pct)]">{{ fmtPct(price?.vs_sector_30d_pct) }}</div>
          <div class="text-ink-muted">{{ t("trader.price.vs_sp500_30d") }}</div>
          <div :class="['font-mono', changeClass(price?.vs_sp500_30d_pct)]">{{ fmtPct(price?.vs_sp500_30d_pct) }}</div>
        </div>
      </div>

      <!-- Momentum -->
      <div class="bg-surface border border-subtle rounded-card p-4 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <Gauge class="h-3.5 w-3.5" />
            {{ t("trader.card.momentum") }}
          </div>
          <span :class="['text-[10px] px-1.5 py-0.5 rounded', stalenessClass(staleness('momentum_card'))]">
            {{ stalenessLabel(staleness('momentum_card')) }}
          </span>
        </div>
        <div class="flex items-center gap-2 text-sm">
          <TrendingUp v-if="momentum?.trend === 'bullish'" class="h-4 w-4 text-success-ink" />
          <TrendingDown v-else-if="momentum?.trend === 'bearish'" class="h-4 w-4 text-danger" />
          <span class="capitalize text-ink-primary font-medium">{{ momentum?.trend || "—" }}</span>
        </div>
        <ul class="text-xs space-y-1">
          <li v-if="momentum?.above_50dma !== null && momentum?.above_50dma !== undefined">
            <span :class="momentum.above_50dma ? 'text-success-ink' : 'text-danger'">
              {{ momentum.above_50dma ? '✓' : '✗' }}
            </span>
            {{ t("trader.momentum.above_50dma") }}
          </li>
          <li v-if="momentum?.above_200dma !== null && momentum?.above_200dma !== undefined">
            <span :class="momentum.above_200dma ? 'text-success-ink' : 'text-danger'">
              {{ momentum.above_200dma ? '✓' : '✗' }}
            </span>
            {{ t("trader.momentum.above_200dma") }}
          </li>
          <li v-if="momentum?.ma_crossover_recent === 'golden_cross'" class="text-success-ink">
            ⚡ {{ t("trader.momentum.golden_cross") }}
          </li>
          <li v-else-if="momentum?.ma_crossover_recent === 'death_cross'" class="text-danger">
            ⚡ {{ t("trader.momentum.death_cross") }}
          </li>
        </ul>
        <div v-if="momentum?.breakout_signals?.length" class="text-xs">
          <span class="text-ink-muted">{{ t("trader.momentum.signals") }}:</span>
          {{ momentum.breakout_signals.join(", ") }}
        </div>
        <div v-if="momentum?.notable_levels" class="text-xs text-ink-muted">
          {{ t("trader.momentum.support") }}: {{ fmtPrice(momentum.notable_levels.support, price?.currency) }} ·
          {{ t("trader.momentum.resistance") }}: {{ fmtPrice(momentum.notable_levels.resistance, price?.currency) }}
        </div>
      </div>

      <!-- Sentiment -->
      <div class="bg-surface border border-subtle rounded-card p-4 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <Users class="h-3.5 w-3.5" />
            {{ t("trader.card.sentiment") }}
          </div>
          <span :class="['text-[10px] px-1.5 py-0.5 rounded', stalenessClass(staleness('sentiment_card'))]">
            {{ stalenessLabel(staleness('sentiment_card')) }}
          </span>
        </div>
        <div class="text-sm text-ink-primary font-medium">
          {{ sentiment?.analyst_consensus || "—" }}
          <span v-if="sentiment?.coverage_count" class="text-ink-muted text-xs ml-1">
            · {{ t("trader.sentiment.coverage", { n: sentiment.coverage_count }) }}
          </span>
        </div>
        <div v-if="sentiment?.rating_distribution" class="flex gap-1 text-[10px]">
          <span v-if="sentiment.rating_distribution.strong_buy" class="px-1.5 py-0.5 rounded bg-success-soft text-success-ink">
            SB · {{ fmtCount(sentiment.rating_distribution.strong_buy) }}
          </span>
          <span v-if="sentiment.rating_distribution.buy" class="px-1.5 py-0.5 rounded bg-success-soft text-success-ink">
            B · {{ fmtCount(sentiment.rating_distribution.buy) }}
          </span>
          <span v-if="sentiment.rating_distribution.hold" class="px-1.5 py-0.5 rounded bg-surface-muted text-ink-secondary">
            H · {{ fmtCount(sentiment.rating_distribution.hold) }}
          </span>
          <span v-if="sentiment.rating_distribution.sell" class="px-1.5 py-0.5 rounded bg-danger/10 text-danger">
            S · {{ fmtCount(sentiment.rating_distribution.sell) }}
          </span>
          <span v-if="sentiment.rating_distribution.strong_sell" class="px-1.5 py-0.5 rounded bg-danger/10 text-danger">
            SS · {{ fmtCount(sentiment.rating_distribution.strong_sell) }}
          </span>
        </div>
        <div v-if="sentiment?.target_price?.mean" class="text-xs">
          <span class="text-ink-muted">{{ t("trader.sentiment.target") }}:</span>
          <span class="font-mono text-ink-primary ml-1">
            {{ fmtPrice(sentiment.target_price.mean, price?.currency) }}
          </span>
          <span class="text-ink-muted ml-1">
            ({{ t("trader.sentiment.target_range", {
              high: fmtPrice(sentiment.target_price.high, price?.currency),
              low: fmtPrice(sentiment.target_price.low, price?.currency),
            }) }})
          </span>
        </div>
        <div v-if="sentiment?.recent_rating_changes?.length" class="text-xs space-y-0.5">
          <div class="text-ink-muted text-[10px] uppercase tracking-wide">
            {{ t("trader.sentiment.recent_changes") }}
          </div>
          <ul class="text-ink-secondary">
            <li v-for="(rc, i) in sentiment.recent_rating_changes.slice(0, 3)" :key="i">
              {{ rc.firm }}: {{ rc.action }} {{ rc.from ? `${rc.from} → ` : '' }}{{ rc.to || '' }}
              <span v-if="rc.target" class="text-ink-muted">· tgt {{ fmtPrice(rc.target, price?.currency) }}</span>
            </li>
          </ul>
        </div>
        <div v-else-if="sentiment" class="text-xs text-ink-muted italic">
          {{ t("trader.sentiment.no_changes") }}
        </div>
      </div>

      <!-- Heat -->
      <div class="bg-surface border border-subtle rounded-card p-4 space-y-1.5 md:col-span-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <Flame class="h-3.5 w-3.5" />
            {{ t("trader.card.heat") }}
          </div>
          <span :class="['text-[10px] px-1.5 py-0.5 rounded', stalenessClass(staleness('heat_card'))]">
            {{ stalenessLabel(staleness('heat_card')) }}
          </span>
        </div>
        <div class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <div class="text-ink-muted">{{ t("trader.heat.rel_volume") }}</div>
          <div class="font-mono text-ink-primary">{{ heat?.rel_volume_20d != null ? `${heat.rel_volume_20d.toFixed(2)}×` : "—" }}</div>
          <div class="text-ink-muted">{{ t("trader.heat.iv_30d") }}</div>
          <div class="font-mono text-ink-primary">
            {{ heat?.iv_30d_pct != null ? `${heat.iv_30d_pct.toFixed(1)}%` : "—" }}
            <span v-if="heat?.iv_percentile_1y != null" class="text-ink-muted">
              · {{ t("trader.heat.iv_percentile", { p: heat.iv_percentile_1y }) }}
            </span>
          </div>
          <div class="text-ink-muted">{{ t("trader.heat.options_skew") }}</div>
          <div class="text-ink-primary">{{ skewLabel(heat?.options_skew) }}</div>
          <div class="text-ink-muted">{{ t("trader.heat.news_flow") }}</div>
          <div class="font-mono text-ink-primary">{{ fmtCount(heat?.news_flow_24h) }}</div>
          <div class="text-ink-muted">{{ t("trader.heat.insiders_30d") }}</div>
          <div class="text-ink-primary">
            <span v-if="heat?.insider_activity_30d">
              {{ heat.insider_activity_30d.buys || 0 }} buys ·
              {{ heat.insider_activity_30d.sells || 0 }} sells
            </span>
            <span v-else>—</span>
          </div>
          <div class="text-ink-muted">{{ t("trader.heat.short_interest") }}</div>
          <div class="font-mono text-ink-primary">{{ fmtPct(heat?.short_interest_pct_float) }}</div>
          <div class="text-ink-muted">{{ t("trader.heat.days_to_cover") }}</div>
          <div class="font-mono text-ink-primary">{{ heat?.days_to_cover != null ? heat.days_to_cover.toFixed(1) : "—" }}</div>
          <div class="text-ink-muted">{{ t("trader.heat.social") }}</div>
          <div class="text-ink-primary">{{ socialLabel(heat?.social_mentions_trend) }}</div>
        </div>
      </div>

      <!-- Catalysts -->
      <div class="bg-surface border border-subtle rounded-card p-4 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <CalendarClock class="h-3.5 w-3.5" />
            {{ t("trader.card.catalysts") }}
          </div>
          <span :class="['text-[10px] px-1.5 py-0.5 rounded', stalenessClass(staleness('catalysts'))]">
            {{ stalenessLabel(staleness('catalysts')) }}
          </span>
        </div>
        <ul v-if="catalysts.length" class="space-y-2 text-xs">
          <li v-for="(c, i) in catalysts" :key="i" class="flex items-start gap-2">
            <span class="font-mono text-ink-muted whitespace-nowrap">{{ c.date }}</span>
            <span :class="['text-[10px] px-1.5 py-0.5 rounded', impactClass(c.est_impact)]" v-if="c.est_impact">
              {{ impactLabel(c.est_impact) }}
            </span>
            <span class="text-ink-primary">
              {{ catalystTypeLabel(c.type) }} · {{ c.title }}
            </span>
          </li>
        </ul>
        <div v-else class="text-xs text-ink-muted italic">{{ t("trader.catalysts.empty") }}</div>
      </div>

      <!-- Trader news -->
      <div class="bg-surface border border-subtle rounded-card p-4 space-y-2 md:col-span-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <Newspaper class="h-3.5 w-3.5" />
            {{ t("trader.card.news") }}
          </div>
          <span :class="['text-[10px] px-1.5 py-0.5 rounded', stalenessClass(staleness('trader_news'))]">
            {{ stalenessLabel(staleness('trader_news')) }}
          </span>
        </div>
        <ul v-if="traderNews.length" class="space-y-2 text-sm">
          <li v-for="(n, i) in traderNews" :key="i" class="flex items-start gap-2">
            <span :class="['text-[10px] px-1.5 py-0.5 rounded mt-0.5 shrink-0', biasClass(n.bias)]">
              {{ biasLabel(n.bias) || "—" }}
            </span>
            <div class="min-w-0 flex-1">
              <a
                v-if="n.source_url"
                :href="n.source_url"
                target="_blank"
                rel="noopener"
                class="text-ink-primary hover:text-accent-hover focus-ring rounded"
              >
                {{ n.headline }}
              </a>
              <span v-else class="text-ink-primary">{{ n.headline }}</span>
              <div v-if="n.summary" class="text-xs text-ink-secondary mt-0.5">{{ n.summary }}</div>
              <div v-if="n.date" class="text-[10px] text-ink-muted mt-0.5 font-mono">{{ n.date }}</div>
            </div>
          </li>
        </ul>
        <div v-else class="text-xs text-ink-muted italic">{{ t("trader.news.empty") }}</div>
      </div>
    </div>
  </section>
</template>
