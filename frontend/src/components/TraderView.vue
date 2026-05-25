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
  BarChart3,
  Boxes,
  Brain,
  CalendarClock,
  CircleDollarSign,
  ClipboardList,
  Flame,
  Gauge,
  Loader2,
  Network,
  Newspaper,
  Radar,
  RefreshCw,
  Target,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
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
  // Page-level language ("en" | "zh"). Optional — falls back to the
  // global appLanguage when absent.
  language: { type: String, default: null },
});
const emit = defineEmits(["refreshed"]);

// Bilingual field picker — mirrors iOS TraderLocalizedText.pick. The
// server now emits paired `<base>_en` / `<base>_zh` for every prose
// field, and keeps the legacy single-language `<base>` as a back-compat
// mirror of the English value. We prefer the user's locale, fall back
// to the other language, and finally to the legacy field.
//
// Effective language: the page-level selection (CompanyDetail's
// per-page EN/中 toggle, which itself syncs from the global app
// language) is passed down as the `language` prop and takes precedence.
// Fall back to the global appLanguage when mounted without a prop.
const lang = computed(() => props.language || appLanguage.value);

function pickLocalized(obj, base) {
  if (!obj) return "";
  const en = obj[`${base}_en`];
  const zh = obj[`${base}_zh`];
  const fallback = obj[base];
  const order =
    lang.value === "zh" ? [zh, en, fallback] : [en, fallback, zh];
  for (const v of order) {
    if (typeof v === "string" && v.trim()) return v;
  }
  return "";
}

function pickLocalizedArray(obj, base) {
  if (!obj) return [];
  const en = obj[`${base}_en`];
  const zh = obj[`${base}_zh`];
  const fallback = obj[base];
  const order =
    lang.value === "zh" ? [zh, en, fallback] : [en, fallback, zh];
  for (const v of order) {
    if (Array.isArray(v) && v.length) return v;
  }
  return [];
}

const refreshing = ref(false);
const refreshError = ref(null);
const liveStatus = ref("");
let activeStream = null;

const snapshot = computed(() => props.company.trader_snapshot || null);
const refreshedAt = computed(() => snapshot.value?.refreshed_at || null);
const marketSession = computed(() => snapshot.value?.market_session || null);

function staleness(cardKey) {
  return cardStaleness(refreshedAt.value, cardKey, marketSession.value);
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

// schema_version 1 (or missing) is the legacy heat_card. The server's
// startup migration nulls heat_card on those records, so a non-null
// heat_card here is always v2. Surface a one-line banner when we
// detect a legacy snapshot so the user knows to refresh.
const traderSchemaVersion = computed(() =>
  snapshot.value?.schema_version ?? 1,
);
const needsForceRefresh = computed(
  () => traderSchemaVersion.value < 2 && snapshot.value !== null,
);

// Bilingual prose pickers — same fallback chain as the rest of the
// trader cards (user locale → other locale → legacy field if any).
function localizedPickAvwap(anchor) {
  return pickLocalized(anchor, "label");
}

// Confidence badge → CSS + label key.
function confidenceClass(c) {
  if (c === "high") return "bg-success-soft text-success-ink";
  if (c === "medium") return "bg-warning-soft text-warning-ink";
  if (c === "low") return "bg-surface-muted text-ink-secondary";
  if (c === "unavailable") return "bg-danger/10 text-danger";
  return "bg-surface-muted text-ink-muted";
}
function confidenceLabel(c) {
  if (c === "high") return t("trader.heat.confidence.high");
  if (c === "medium") return t("trader.heat.confidence.medium");
  if (c === "low") return t("trader.heat.confidence.low");
  if (c === "unavailable") return t("trader.heat.confidence.unavailable");
  return "";
}

// Section is "unavailable" → render the confidence_note instead of
// trying to lay out null number cells. Returns the bilingual note.
function sectionUnavailableNote(sec) {
  if (!sec || sec.confidence !== "unavailable") return null;
  return pickLocalized(sec, "confidence_note") || null;
}

// Returns true when a section sub-object has zero useful data.
function hasNoData(sec) {
  return sec == null;
}

// Anchored VWAPs — current price + table of anchors with delta vs current.
function anchorDeltaPct(anchor, currentPrice) {
  if (anchor?.price == null || currentPrice == null) return null;
  return ((currentPrice - anchor.price) / anchor.price) * 100;
}
function anchorKindLabel(kind) {
  return t(`trader.heat.avwap.kind.${kind || "other"}`);
}

// Float turnover bar width — clamp to 0..100 so a malformed pct_float
// can't blow out the row.
function zoneBarWidth(pctFloat) {
  if (pctFloat == null || !isFinite(pctFloat)) return 0;
  return Math.min(100, Math.max(0, pctFloat));
}

// Holder mix rows — drop zero buckets so a thinly-covered name
// doesn't render five "0%" lines.
const holderMixRows = computed(() => {
  const m = heat.value?.holder_mix;
  if (!m) return [];
  const buckets = [
    ["passive", m.passive_pct],
    ["long_only", m.long_only_pct],
    ["hedge_fund", m.hedge_fund_pct],
    ["retail", m.retail_pct],
    ["insider", m.insider_pct],
    ["strategic", m.strategic_pct],
  ];
  return buckets
    .filter(([, v]) => v != null && v > 0)
    .map(([key, v]) => ({
      label: t(`trader.heat.holder.${key}`),
      pct: v,
    }));
});

// Options regime — show whether current price sits above/below the
// gamma flip. Falls back to whatever regime_en/zh the model wrote.
function optionsRegimeText(opt, currentPrice) {
  const written = pickLocalized(opt, "regime");
  if (written) return written;
  if (currentPrice == null || opt?.gamma_flip == null) {
    return t("trader.heat.options.regime_unknown");
  }
  return currentPrice >= opt.gamma_flip
    ? t("trader.heat.options.regime_above")
    : t("trader.heat.options.regime_below");
}

function shortTrendArrow(trend) {
  if (trend === "rising") return t("trader.heat.short.trend_rising");
  if (trend === "falling") return t("trader.heat.short.trend_falling");
  if (trend === "flat") return t("trader.heat.short.trend_flat");
  return "";
}

function revisionsArrow(direction) {
  if (direction === "up") return t("trader.heat.rev.up");
  if (direction === "down") return t("trader.heat.rev.down");
  if (direction === "mixed") return t("trader.heat.rev.mixed");
  return "";
}

function fragilityRatingLabel(rating) {
  if (rating === "low") return t("trader.heat.fragility.low");
  if (rating === "medium") return t("trader.heat.fragility.medium");
  if (rating === "high") return t("trader.heat.fragility.high");
  if (rating === "extreme") return t("trader.heat.fragility.extreme");
  return "—";
}

async function onForceRefresh() {
  refreshing.value = true;
  refreshError.value = null;
  liveStatus.value = "";
  try {
    const job = await api.trader.refresh(props.company.id, { force: true });
    openStream(job.stream_url);
  } catch (e) {
    refreshing.value = false;
    refreshError.value = e?.message || t("trader.refresh_failed");
  }
}

const catalysts = computed(() => snapshot.value?.catalysts || []);
const traderNews = computed(() => snapshot.value?.trader_news || []);
const researchOverview = computed(() => snapshot.value?.research_overview || null);
const businessMix = computed(() => researchOverview.value?.business_mix || null);
const financialQuality = computed(() =>
  researchOverview.value?.financial_quality || null,
);
const growthDurability = computed(() =>
  researchOverview.value?.growth_durability || null,
);
const peerContext = computed(() => researchOverview.value?.peer_context || null);
const scenarioMatrix = computed(() =>
  researchOverview.value?.scenario_matrix || null,
);
const diligenceQuestions = computed(() =>
  researchOverview.value?.diligence_questions || null,
);
const hasResearchOverview = computed(() =>
  Boolean(
    businessMix.value ||
      financialQuality.value ||
      growthDurability.value ||
      peerContext.value ||
      scenarioMatrix.value ||
      diligenceQuestions.value,
  ),
);

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

function fmtPlainPct(v, digits = 1) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

function fmtBp(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${Math.round(n)} bp`;
}

function pctWidth(v, fallback = 0) {
  const n = Number(v);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(100, Math.max(0, n));
}

function signedBarWidth(v) {
  const n = Math.abs(Number(v));
  if (!Number.isFinite(n)) return 0;
  return Math.min(100, Math.max(6, n * 1.5));
}

const segmentColors = [
  "bg-accent",
  "bg-success",
  "bg-warning",
  "bg-danger",
  "bg-ink-muted",
  "bg-accent-hover",
];

function segmentColor(i) {
  return segmentColors[i % segmentColors.length];
}

function scoreToneClass(score) {
  const n = Number(score);
  if (!Number.isFinite(n)) return "bg-surface-muted text-ink-muted";
  if (n >= 70) return "bg-success-soft text-success-ink";
  if (n >= 45) return "bg-warning-soft text-warning-ink";
  return "bg-danger/10 text-danger";
}

function metricToneClass(direction) {
  if (direction === "strong") return "bg-success";
  if (direction === "weak") return "bg-danger";
  return "bg-warning";
}

function metricTextClass(direction) {
  if (direction === "strong") return "text-success-ink";
  if (direction === "weak") return "text-danger";
  return "text-warning-ink";
}

function mixSignalLabel(signal) {
  if (!signal) return "";
  return t(`trader.research.signal_${signal}`);
}

function peerCompanyName(peer) {
  if (!peer) return "";
  if (lang.value === "zh") return peer.company_zh || peer.company_en || peer.ticker;
  return peer.company_en || peer.company_zh || peer.ticker;
}

function scenarioLabel(scenario) {
  if (!scenario) return "";
  return pickLocalized(scenario, "label") ||
    t(`trader.research.case_${scenario.case || "base"}`);
}

function scenarioToneClass(kind) {
  if (kind === "bull") return "bg-success-soft text-success-ink";
  if (kind === "bear") return "bg-danger/10 text-danger";
  return "bg-accent-soft text-accent-ink";
}

function severityClass(severity) {
  if (severity === "critical") return "bg-danger/10 text-danger";
  if (severity === "important") return "bg-warning-soft text-warning-ink";
  return "bg-surface-muted text-ink-secondary";
}

function severityLabel(severity) {
  if (severity === "critical") return t("trader.research.severity_critical");
  if (severity === "important") return t("trader.research.severity_important");
  return t("trader.research.severity_watch");
}

function sourceLabel(section) {
  if (!section?.source_url) return "";
  return t("trader.research.source");
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
          <span class="capitalize text-ink-primary font-medium">{{ pickLocalized(momentum, 'trend') || "—" }}</span>
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
        <div v-if="pickLocalizedArray(momentum, 'breakout_signals').length" class="text-xs">
          <span class="text-ink-muted">{{ t("trader.momentum.signals") }}:</span>
          {{ pickLocalizedArray(momentum, 'breakout_signals').join(", ") }}
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
          {{ pickLocalized(sentiment, 'analyst_consensus') || "—" }}
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
              {{ rc.firm }}: {{ pickLocalized(rc, 'action') }}
              <template v-if="pickLocalized(rc, 'from')">{{ pickLocalized(rc, 'from') }} → </template>{{ pickLocalized(rc, 'to') }}
              <span v-if="rc.target" class="text-ink-muted">· tgt {{ fmtPrice(rc.target, price?.currency) }}</span>
            </li>
          </ul>
        </div>
        <div v-else-if="sentiment" class="text-xs text-ink-muted italic">
          {{ t("trader.sentiment.no_changes") }}
        </div>
      </div>

      <!-- Positioning Structure (heat_card v2) — widest card, 2 cols -->
      <div class="bg-surface border border-subtle rounded-card p-4 space-y-3 md:col-span-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <Flame class="h-3.5 w-3.5" />
            {{ t("trader.card.heat.v2") }}
          </div>
          <span :class="['text-[10px] px-1.5 py-0.5 rounded', stalenessClass(staleness('heat_card'))]">
            {{ stalenessLabel(staleness('heat_card')) }}
          </span>
        </div>

        <!-- Legacy snapshot detected — refresh needed for v2 shape. -->
        <div
          v-if="needsForceRefresh"
          class="text-xs italic text-warning-ink bg-warning-soft rounded p-2 flex items-center justify-between gap-2"
        >
          <span class="min-w-0">{{ t("trader.heat.v2.refresh_required") }}</span>
          <button
            type="button"
            class="text-[11px] font-semibold underline shrink-0 focus-ring rounded"
            @click="onForceRefresh"
            :disabled="refreshing"
          >
            {{ t("trader.heat.v2.force_refresh") }}
          </button>
        </div>

        <div v-else-if="!heat" class="text-xs text-ink-muted italic">
          {{ t("trader.heat.v2.empty") }}
        </div>

        <template v-else>
          <!-- 1. Anchored cost basis -->
          <section v-if="heat.anchored_vwaps" class="space-y-1.5">
            <div class="flex items-center justify-between">
              <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                {{ t("trader.heat.section.anchored_vwaps") }}
              </span>
              <span
                :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(heat.anchored_vwaps.confidence)]"
              >
                {{ confidenceLabel(heat.anchored_vwaps.confidence) }}
              </span>
            </div>
            <template v-if="sectionUnavailableNote(heat.anchored_vwaps)">
              <div class="text-[11px] text-ink-muted italic">
                {{ sectionUnavailableNote(heat.anchored_vwaps) }}
              </div>
            </template>
            <template v-else>
              <div class="text-sm font-mono text-ink-primary">
                {{ t("trader.heat.avwap.current") }}
                {{ fmtPrice(heat.anchored_vwaps.current_price, price?.currency) }}
              </div>
              <ul class="space-y-0.5 text-[11px]">
                <li
                  v-for="(a, i) in (heat.anchored_vwaps.anchors || [])"
                  :key="i"
                  class="flex items-baseline gap-1"
                >
                  <span class="text-ink-muted">
                    {{ t("trader.heat.avwap.vs") }} {{ localizedPickAvwap(a) || anchorKindLabel(a.kind) }}
                  </span>
                  <span class="font-mono text-ink-primary">
                    {{ fmtPrice(a.price, price?.currency) }}
                  </span>
                  <span
                    v-if="anchorDeltaPct(a, heat.anchored_vwaps.current_price) != null"
                    :class="['font-mono', changeClass(anchorDeltaPct(a, heat.anchored_vwaps.current_price))]"
                  >
                    {{ fmtPct(anchorDeltaPct(a, heat.anchored_vwaps.current_price)) }}
                  </span>
                </li>
              </ul>
            </template>
          </section>

          <!-- 2. Float turnover zones -->
          <section v-if="heat.float_turnover_zones" class="space-y-1.5">
            <div class="flex items-center justify-between">
              <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                {{ t("trader.heat.section.float_turnover_zones") }}
              </span>
              <span
                :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(heat.float_turnover_zones.confidence)]"
              >
                {{ confidenceLabel(heat.float_turnover_zones.confidence) }}
              </span>
            </div>
            <template v-if="sectionUnavailableNote(heat.float_turnover_zones)">
              <div class="text-[11px] text-ink-muted italic">
                {{ sectionUnavailableNote(heat.float_turnover_zones) }}
              </div>
            </template>
            <template v-else>
              <ul class="space-y-1.5 text-[11px]">
                <li
                  v-for="(z, i) in (heat.float_turnover_zones.zones || [])"
                  :key="i"
                  class="space-y-0.5 min-w-0"
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <span class="font-mono text-ink-primary shrink-0">
                      {{ fmtPrice(z.low, price?.currency) }}–{{ fmtPrice(z.high, price?.currency) }}
                    </span>
                    <div class="flex-1 bg-surface-muted h-1.5 rounded overflow-hidden">
                      <div
                        class="h-full bg-accent/70"
                        :style="{ width: zoneBarWidth(z.pct_float) + '%' }"
                      />
                    </div>
                    <span class="font-mono text-ink-secondary shrink-0">
                      {{ z.pct_float != null ? z.pct_float.toFixed(0) + '%' : '—' }}
                    </span>
                  </div>
                  <div
                    v-if="pickLocalized(z, 'note')"
                    class="text-[11px] text-ink-secondary leading-snug"
                  >
                    {{ pickLocalized(z, "note") }}
                  </div>
                </li>
              </ul>
              <!-- When pct_float is unsourceable the model explains why
                   in confidence_note (often at 'low', not 'unavailable',
                   so sectionUnavailableNote doesn't catch it). Surface it
                   so the row of "—" isn't mistaken for missing data. -->
              <div
                v-if="
                  heat.float_turnover_zones.confidence !== 'high' &&
                  pickLocalized(heat.float_turnover_zones, 'confidence_note')
                "
                class="text-[10px] text-ink-muted italic leading-snug"
              >
                {{ pickLocalized(heat.float_turnover_zones, "confidence_note") }}
              </div>
            </template>
          </section>

          <!-- 3. Holder mix + 4. Options regime (side by side) -->
          <section
            v-if="heat.holder_mix || heat.options_positioning"
            class="grid grid-cols-2 gap-x-3 gap-y-1.5"
          >
            <div v-if="heat.holder_mix" class="space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                  {{ t("trader.heat.section.holder_mix") }}
                </span>
                <span
                  :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(heat.holder_mix.confidence)]"
                >
                  {{ confidenceLabel(heat.holder_mix.confidence) }}
                </span>
              </div>
              <template v-if="sectionUnavailableNote(heat.holder_mix)">
                <div class="text-[11px] text-ink-muted italic">
                  {{ sectionUnavailableNote(heat.holder_mix) }}
                </div>
              </template>
              <template v-else>
                <ul class="text-[11px] space-y-0.5">
                  <li
                    v-for="(row, i) in holderMixRows"
                    :key="i"
                    class="flex justify-between"
                  >
                    <span class="text-ink-muted">{{ row.label }}</span>
                    <span class="font-mono text-ink-primary">{{ row.pct.toFixed(0) }}%</span>
                  </li>
                </ul>
                <div
                  v-if="pickLocalized(heat.holder_mix, 'quality_label')"
                  class="text-[11px] text-ink-secondary italic mt-1"
                >
                  {{ pickLocalized(heat.holder_mix, "quality_label") }}
                </div>
              </template>
            </div>

            <div v-if="heat.options_positioning" class="space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                  {{ t("trader.heat.section.options_positioning") }}
                </span>
                <span
                  :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(heat.options_positioning.confidence)]"
                >
                  {{ confidenceLabel(heat.options_positioning.confidence) }}
                </span>
              </div>
              <template v-if="sectionUnavailableNote(heat.options_positioning)">
                <div class="text-[11px] text-ink-muted italic">
                  {{ sectionUnavailableNote(heat.options_positioning) }}
                </div>
              </template>
              <template v-else>
                <ul class="text-[11px] space-y-0.5">
                  <li class="flex justify-between">
                    <span class="text-ink-muted">{{ t("trader.heat.options.gamma_flip") }}</span>
                    <span class="font-mono text-ink-primary">
                      {{ fmtPrice(heat.options_positioning.gamma_flip, price?.currency) }}
                    </span>
                  </li>
                  <li class="flex justify-between">
                    <span class="text-ink-muted">{{ t("trader.heat.options.put_wall") }}</span>
                    <span class="font-mono text-ink-primary">
                      {{ fmtPrice(heat.options_positioning.put_wall, price?.currency) }}
                    </span>
                  </li>
                  <li class="flex justify-between">
                    <span class="text-ink-muted">{{ t("trader.heat.options.call_wall") }}</span>
                    <span class="font-mono text-ink-primary">
                      {{ fmtPrice(heat.options_positioning.call_wall, price?.currency) }}
                    </span>
                  </li>
                </ul>
                <div class="text-[11px] text-ink-secondary italic">
                  {{ optionsRegimeText(heat.options_positioning, heat.anchored_vwaps?.current_price) }}
                </div>
              </template>
            </div>
          </section>

          <!-- 5. Short pressure + 6. Valuation -->
          <section
            v-if="heat.short_pressure || heat.valuation"
            class="grid grid-cols-2 gap-x-3 gap-y-1.5"
          >
            <div v-if="heat.short_pressure" class="space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                  {{ t("trader.heat.section.short_pressure") }}
                </span>
                <span
                  :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(heat.short_pressure.confidence)]"
                >
                  {{ confidenceLabel(heat.short_pressure.confidence) }}
                </span>
              </div>
              <template v-if="sectionUnavailableNote(heat.short_pressure)">
                <div class="text-[11px] text-ink-muted italic">
                  {{ sectionUnavailableNote(heat.short_pressure) }}
                </div>
              </template>
              <template v-else>
                <ul class="text-[11px] space-y-0.5">
                  <li class="flex justify-between">
                    <span class="text-ink-muted">{{ t("trader.heat.short.si") }}</span>
                    <span class="font-mono text-ink-primary">
                      {{ fmtPct(heat.short_pressure.si_pct_float) }}
                    </span>
                  </li>
                  <li class="flex justify-between">
                    <span class="text-ink-muted">{{ t("trader.heat.short.dtc") }}</span>
                    <span class="font-mono text-ink-primary">
                      {{ heat.short_pressure.days_to_cover != null ? heat.short_pressure.days_to_cover.toFixed(1) : "—" }}
                    </span>
                  </li>
                  <li class="flex justify-between">
                    <span class="text-ink-muted">{{ t("trader.heat.short.borrow") }}</span>
                    <span class="font-mono text-ink-primary">
                      {{ fmtPct(heat.short_pressure.borrow_rate_pct) }}
                      <span class="text-ink-muted ml-0.5">{{ shortTrendArrow(heat.short_pressure.trend) }}</span>
                    </span>
                  </li>
                </ul>
                <div
                  v-if="pickLocalized(heat.short_pressure, 'note')"
                  class="text-[11px] text-ink-secondary italic"
                >
                  {{ pickLocalized(heat.short_pressure, "note") }}
                </div>
              </template>
            </div>

            <div v-if="heat.valuation" class="space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                  {{ t("trader.heat.section.valuation") }}
                </span>
                <span
                  :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(heat.valuation.confidence)]"
                >
                  {{ confidenceLabel(heat.valuation.confidence) }}
                </span>
              </div>
              <template v-if="sectionUnavailableNote(heat.valuation)">
                <div class="text-[11px] text-ink-muted italic">
                  {{ sectionUnavailableNote(heat.valuation) }}
                </div>
              </template>
              <template v-else>
                <ul class="text-[11px] space-y-0.5">
                  <li class="flex justify-between gap-1">
                    <span class="text-ink-muted">{{ t("trader.heat.val.ev_revenue") }}</span>
                    <span class="font-mono text-ink-primary min-w-0 truncate text-right">
                      {{ heat.valuation.ev_revenue_current != null ? `${heat.valuation.ev_revenue_current.toFixed(1)}×` : "—" }}
                      <span v-if="heat.valuation.ev_revenue_5y_percentile != null" class="text-ink-muted">
                        {{ t("trader.heat.val.ev_revenue_pct", { p: heat.valuation.ev_revenue_5y_percentile }) }}
                      </span>
                    </span>
                  </li>
                  <li class="flex justify-between">
                    <span class="text-ink-muted">{{ t("trader.heat.val.fwd_ev_ebitda") }}</span>
                    <span class="font-mono text-ink-primary">
                      {{ heat.valuation.fwd_ev_ebitda != null ? `${heat.valuation.fwd_ev_ebitda.toFixed(1)}×` : "—" }}
                    </span>
                  </li>
                  <li class="flex justify-between">
                    <span class="text-ink-muted">{{ t("trader.heat.val.peg") }}</span>
                    <span class="font-mono text-ink-primary">
                      {{ heat.valuation.peg != null ? `${heat.valuation.peg.toFixed(2)}×` : "—" }}
                    </span>
                  </li>
                </ul>
                <div
                  v-if="pickLocalized(heat.valuation, 'note')"
                  class="text-[11px] text-ink-secondary italic"
                >
                  {{ pickLocalized(heat.valuation, "note") }}
                </div>
              </template>
            </div>
          </section>

          <!-- 7. Revisions + 8. Next catalyst -->
          <section
            v-if="heat.revisions || heat.next_catalyst"
            class="grid grid-cols-2 gap-x-3 gap-y-1.5"
          >
            <div v-if="heat.revisions" class="space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                  {{ t("trader.heat.section.revisions") }}
                </span>
                <span
                  :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(heat.revisions.confidence)]"
                >
                  {{ confidenceLabel(heat.revisions.confidence) }}
                </span>
              </div>
              <template v-if="sectionUnavailableNote(heat.revisions)">
                <div class="text-[11px] text-ink-muted italic">
                  {{ sectionUnavailableNote(heat.revisions) }}
                </div>
              </template>
              <template v-else>
                <div class="text-[11px] font-mono text-ink-primary">
                  {{ t("trader.heat.rev.30d", {
                    up: heat.revisions.eps_up_30d ?? "—",
                    down: heat.revisions.eps_down_30d ?? "—",
                  }) }}
                  <span class="text-ink-muted">{{ revisionsArrow(heat.revisions.direction) }}</span>
                </div>
                <div class="text-[11px] font-mono text-ink-primary">
                  {{ t("trader.heat.rev.90d", {
                    up: heat.revisions.eps_up_90d ?? "—",
                    down: heat.revisions.eps_down_90d ?? "—",
                  }) }}
                </div>
                <div
                  v-if="pickLocalized(heat.revisions, 'note')"
                  class="text-[11px] text-ink-secondary italic"
                >
                  {{ pickLocalized(heat.revisions, "note") }}
                </div>
              </template>
            </div>

            <div v-if="heat.next_catalyst" class="space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                  {{ t("trader.heat.section.next_catalyst") }}
                </span>
                <span
                  :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(heat.next_catalyst.confidence)]"
                >
                  {{ confidenceLabel(heat.next_catalyst.confidence) }}
                </span>
              </div>
              <template v-if="sectionUnavailableNote(heat.next_catalyst)">
                <div class="text-[11px] text-ink-muted italic">
                  {{ sectionUnavailableNote(heat.next_catalyst) }}
                </div>
              </template>
              <template v-else>
                <div class="text-[11px] text-ink-primary">
                  {{ pickLocalized(heat.next_catalyst, "label") }}
                  <span v-if="heat.next_catalyst.date" class="text-ink-muted">
                    · {{ heat.next_catalyst.date }}
                  </span>
                </div>
                <div
                  v-if="heat.next_catalyst.implied_move_pct != null"
                  class="text-[11px] font-mono text-ink-primary"
                >
                  {{ t("trader.heat.cat.implied_move", {
                    pct: heat.next_catalyst.implied_move_pct.toFixed(1),
                  }) }}
                </div>
              </template>
            </div>
          </section>

          <!-- Composites: support confidence + fragility + repricing risk -->
          <section v-if="heat.support_confidence" class="space-y-1">
            <div class="text-[10px] uppercase tracking-wide text-ink-muted">
              {{ t("trader.heat.section.support_confidence") }}
            </div>
            <ul class="space-y-0.5 text-[11px]">
              <li
                v-for="(z, i) in (heat.support_confidence.zones || [])"
                :key="i"
                class="flex items-baseline gap-2 min-w-0"
              >
                <span class="font-mono text-ink-primary shrink-0">
                  {{ fmtPrice(z.low, price?.currency) }}–{{ fmtPrice(z.high, price?.currency) }}
                </span>
                <span
                  :class="['text-[9px] uppercase px-1 py-0.5 rounded shrink-0', confidenceClass(z.confidence)]"
                >
                  {{ confidenceLabel(z.confidence) }}
                </span>
                <span class="text-ink-secondary min-w-0 truncate">
                  {{ (pickLocalizedArray(z, "reasons") || []).join(" · ") }}
                </span>
              </li>
            </ul>
          </section>

          <section v-if="heat.fragility" class="space-y-1">
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                {{ t("trader.heat.section.fragility") }}
              </span>
              <span class="font-mono text-ink-primary">
                {{ fragilityRatingLabel(heat.fragility.rating) }}
                <span v-if="heat.fragility.score != null" class="text-ink-muted ml-1">
                  {{ t("trader.heat.fragility.score", { score: heat.fragility.score }) }}
                </span>
              </span>
            </div>
            <div
              v-if="pickLocalizedArray(heat.fragility, 'drivers').length"
              class="text-[11px] text-ink-secondary"
            >
              {{ pickLocalizedArray(heat.fragility, "drivers").join(" · ") }}
            </div>
          </section>

          <section v-if="heat.repricing_risk" class="space-y-1">
            <div class="text-[10px] uppercase tracking-wide text-ink-muted">
              {{ t("trader.heat.section.repricing_risk") }}
            </div>
            <div class="flex flex-wrap gap-1 text-[11px]">
              <span class="px-1.5 py-0.5 rounded bg-success-soft text-success-ink">
                {{ heat.repricing_risk.positive_pct ?? "—" }}% {{ t("trader.heat.repricing.positive") }}
              </span>
              <span class="px-1.5 py-0.5 rounded bg-surface-muted text-ink-secondary">
                {{ heat.repricing_risk.neutral_pct ?? "—" }}% {{ t("trader.heat.repricing.neutral") }}
              </span>
              <span class="px-1.5 py-0.5 rounded bg-danger/10 text-danger">
                {{ heat.repricing_risk.negative_pct ?? "—" }}% {{ t("trader.heat.repricing.negative") }}
              </span>
            </div>
            <div
              v-if="pickLocalized(heat.repricing_risk, 'note')"
              class="text-[11px] text-ink-secondary italic"
            >
              {{ pickLocalized(heat.repricing_risk, "note") }}
            </div>
          </section>
        </template>
      </div>

      <!-- Catalysts — short list (≤5 items), span 2 columns so the row
           descriptions don't wrap awkwardly. -->
      <!-- Upcoming catalysts — 1 col (Positioning Structure takes the other 2) -->
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
              {{ catalystTypeLabel(c.type) }} · {{ pickLocalized(c, 'title') }}
              <span v-if="pickLocalized(c, 'summary')" class="text-ink-secondary block text-[11px] mt-0.5">
                {{ pickLocalized(c, 'summary') }}
              </span>
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
                {{ pickLocalized(n, 'headline') }}
              </a>
              <span v-else class="text-ink-primary">{{ pickLocalized(n, 'headline') }}</span>
              <div v-if="pickLocalized(n, 'summary')" class="text-xs text-ink-secondary mt-0.5">{{ pickLocalized(n, 'summary') }}</div>
              <div v-if="n.date" class="text-[10px] text-ink-muted mt-0.5 font-mono">{{ n.date }}</div>
            </div>
          </li>
        </ul>
        <div v-else class="text-xs text-ink-muted italic">{{ t("trader.news.empty") }}</div>
      </div>

      <!-- Research Overview — second card group with non-tape context. -->
      <section class="md:col-span-3 space-y-3 pt-1">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <Radar class="h-3.5 w-3.5" />
            {{ t("trader.card.research_overview") }}
          </div>
          <div class="flex items-center gap-2 text-[10px] text-ink-muted">
            <span
              v-if="researchOverview?.updated_at"
              class="font-mono"
            >
              {{ t("trader.refreshed_at", { when: relativeAge(researchOverview.updated_at) }) }}
            </span>
            <span :class="['px-1.5 py-0.5 rounded', stalenessClass(staleness('research_overview'))]">
              {{ stalenessLabel(staleness('research_overview')) }}
            </span>
          </div>
        </div>

        <div
          v-if="!hasResearchOverview"
          class="rounded-card border border-dashed border-subtle p-5 text-sm text-ink-secondary text-center"
        >
          {{ t("trader.research.empty") }}
        </div>

        <div v-else class="grid gap-3 lg:grid-cols-3">
          <!-- Business mix -->
          <div
            v-if="businessMix"
            class="bg-surface border border-subtle rounded-card p-4 space-y-3 lg:col-span-2"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <Boxes class="h-3.5 w-3.5" />
                {{ t("trader.research.business_mix") }}
              </div>
              <span
                v-if="businessMix.confidence"
                :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(businessMix.confidence)]"
              >
                {{ confidenceLabel(businessMix.confidence) }}
              </span>
            </div>
            <div v-if="pickLocalized(businessMix, 'headline')" class="text-sm text-ink-primary">
              {{ pickLocalized(businessMix, "headline") }}
            </div>
            <div
              v-if="businessMix.segments?.length"
              class="flex h-3 overflow-hidden rounded bg-surface-muted"
            >
              <div
                v-for="(seg, i) in businessMix.segments"
                :key="i"
                :class="['h-full', segmentColor(i)]"
                :style="{ width: pctWidth(seg.revenue_pct) + '%' }"
              />
            </div>
            <ul v-if="businessMix.segments?.length" class="space-y-2 text-xs">
              <li
                v-for="(seg, i) in businessMix.segments"
                :key="`${i}-${pickLocalized(seg, 'name')}`"
                class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
              >
                <div class="min-w-0">
                  <div class="flex items-center gap-1.5 min-w-0">
                    <span :class="['h-2 w-2 rounded-full shrink-0', segmentColor(i)]" />
                    <span class="font-medium text-ink-primary truncate">
                      {{ pickLocalized(seg, "name") || "—" }}
                    </span>
                    <span
                      v-if="mixSignalLabel(seg.signal)"
                      class="text-[10px] px-1.5 py-0.5 rounded bg-surface-muted text-ink-secondary shrink-0"
                    >
                      {{ mixSignalLabel(seg.signal) }}
                    </span>
                  </div>
                  <div
                    v-if="pickLocalized(seg, 'note')"
                    class="text-[11px] text-ink-secondary mt-0.5 leading-snug"
                  >
                    {{ pickLocalized(seg, "note") }}
                  </div>
                </div>
                <div class="font-mono text-ink-primary sm:text-right whitespace-nowrap">
                  {{ fmtPlainPct(seg.revenue_pct) }}
                  <span :class="['ml-1', changeClass(seg.growth_pct)]">
                    {{ fmtPct(seg.growth_pct) }}
                  </span>
                </div>
              </li>
            </ul>
            <div class="flex items-center justify-between gap-2 text-[10px] text-ink-muted">
              <span v-if="businessMix.confidence !== 'high' && pickLocalized(businessMix, 'confidence_note')">
                {{ pickLocalized(businessMix, "confidence_note") }}
              </span>
              <a
                v-if="businessMix.source_url"
                :href="businessMix.source_url"
                target="_blank"
                rel="noopener"
                class="text-accent hover:text-accent-hover focus-ring rounded ml-auto"
              >
                {{ sourceLabel(businessMix) }}
              </a>
            </div>
          </div>

          <!-- Financial quality -->
          <div
            v-if="financialQuality"
            class="bg-surface border border-subtle rounded-card p-4 space-y-3"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <CircleDollarSign class="h-3.5 w-3.5" />
                {{ t("trader.research.financial_quality") }}
              </div>
              <span
                v-if="financialQuality.confidence"
                :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(financialQuality.confidence)]"
              >
                {{ confidenceLabel(financialQuality.confidence) }}
              </span>
            </div>
            <div class="flex items-end justify-between gap-3">
              <div>
                <div class="text-3xl font-display text-ink-primary leading-none">
                  {{ financialQuality.score ?? "—" }}
                </div>
                <div class="text-[10px] uppercase tracking-wide text-ink-muted mt-1">
                  {{ t("trader.research.quality_score") }}
                </div>
              </div>
              <span :class="['text-[10px] px-1.5 py-0.5 rounded', scoreToneClass(financialQuality.score)]">
                {{ financialQuality.score != null ? `${financialQuality.score}/100` : "—" }}
              </span>
            </div>
            <div class="h-1.5 rounded bg-surface-muted overflow-hidden">
              <div
                class="h-full bg-accent"
                :style="{ width: pctWidth(financialQuality.score) + '%' }"
              />
            </div>
            <p v-if="pickLocalized(financialQuality, 'summary')" class="text-xs text-ink-secondary leading-snug">
              {{ pickLocalized(financialQuality, "summary") }}
            </p>
            <ul v-if="financialQuality.metrics?.length" class="space-y-2 text-xs">
              <li v-for="(m, i) in financialQuality.metrics.slice(0, 5)" :key="i" class="space-y-1">
                <div class="flex items-baseline justify-between gap-2">
                  <span class="text-ink-muted min-w-0 truncate">{{ pickLocalized(m, "label") }}</span>
                  <span :class="['font-mono shrink-0', metricTextClass(m.direction)]">{{ m.value || "—" }}</span>
                </div>
                <div class="h-1 rounded bg-surface-muted overflow-hidden">
                  <div
                    :class="['h-full', metricToneClass(m.direction)]"
                    :style="{ width: pctWidth(m.percentile) + '%' }"
                  />
                </div>
                <div v-if="pickLocalized(m, 'note')" class="text-[11px] text-ink-secondary leading-snug">
                  {{ pickLocalized(m, "note") }}
                </div>
              </li>
            </ul>
          </div>

          <!-- Growth durability -->
          <div
            v-if="growthDurability"
            class="bg-surface border border-subtle rounded-card p-4 space-y-3"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <BarChart3 class="h-3.5 w-3.5" />
                {{ t("trader.research.growth_durability") }}
              </div>
              <span
                v-if="growthDurability.confidence"
                :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(growthDurability.confidence)]"
              >
                {{ confidenceLabel(growthDurability.confidence) }}
              </span>
            </div>
            <p v-if="pickLocalized(growthDurability, 'thesis')" class="text-sm text-ink-primary leading-snug">
              {{ pickLocalized(growthDurability, "thesis") }}
            </p>
            <ul v-if="growthDurability.horizons?.length" class="space-y-2 text-xs">
              <li
                v-for="(h, i) in growthDurability.horizons"
                :key="`${h.period}-${i}`"
                class="space-y-1"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="font-mono text-ink-primary">{{ h.period }}</span>
                  <span class="font-mono text-ink-muted">
                    {{ fmtPlainPct(h.revenue_growth_pct) }} {{ t("trader.research.rev") }} ·
                    {{ fmtPlainPct(h.eps_growth_pct) }} {{ t("trader.research.eps") }}
                  </span>
                </div>
                <div class="grid grid-cols-[52px_minmax(0,1fr)] items-center gap-2">
                  <span class="text-[10px] text-ink-muted">{{ t("trader.research.rev") }}</span>
                  <div class="h-1.5 rounded bg-surface-muted overflow-hidden">
                    <div
                      class="h-full bg-success"
                      :style="{ width: pctWidth(h.revenue_growth_pct, 4) + '%' }"
                    />
                  </div>
                  <span class="text-[10px] text-ink-muted">{{ t("trader.research.eps") }}</span>
                  <div class="h-1.5 rounded bg-surface-muted overflow-hidden">
                    <div
                      class="h-full bg-accent"
                      :style="{ width: pctWidth(h.eps_growth_pct, 4) + '%' }"
                    />
                  </div>
                </div>
                <div class="flex items-start justify-between gap-2 text-[11px]">
                  <span v-if="pickLocalized(h, 'note')" class="text-ink-secondary leading-snug">
                    {{ pickLocalized(h, "note") }}
                  </span>
                  <span :class="['font-mono shrink-0', changeClass(h.margin_delta_bp)]">
                    {{ fmtBp(h.margin_delta_bp) }}
                  </span>
                </div>
              </li>
            </ul>
          </div>

          <!-- Peer context -->
          <div
            v-if="peerContext"
            class="bg-surface border border-subtle rounded-card p-4 space-y-3 lg:col-span-2"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <Network class="h-3.5 w-3.5" />
                {{ t("trader.research.peer_context") }}
              </div>
              <span
                v-if="peerContext.confidence"
                :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(peerContext.confidence)]"
              >
                {{ confidenceLabel(peerContext.confidence) }}
              </span>
            </div>
            <p v-if="pickLocalized(peerContext, 'summary')" class="text-sm text-ink-primary leading-snug">
              {{ pickLocalized(peerContext, "summary") }}
            </p>
            <ul v-if="peerContext.peers?.length" class="space-y-2 text-xs">
              <li
                v-for="(peer, i) in peerContext.peers"
                :key="`${peer.ticker}-${i}`"
                class="grid gap-2 sm:grid-cols-[92px_minmax(0,1fr)_auto] sm:items-center"
              >
                <div class="min-w-0">
                  <div class="font-mono text-ink-primary">{{ peer.ticker }}</div>
                  <div class="text-[10px] text-ink-muted truncate">{{ peerCompanyName(peer) }}</div>
                </div>
                <div class="space-y-1 min-w-0">
                  <div class="h-1.5 rounded bg-surface-muted overflow-hidden">
                    <div class="h-full bg-accent" :style="{ width: pctWidth(peer.score) + '%' }" />
                  </div>
                  <div v-if="pickLocalized(peer, 'note')" class="text-[11px] text-ink-secondary truncate">
                    {{ pickLocalized(peer, "note") }}
                  </div>
                </div>
                <div class="grid grid-cols-3 gap-2 font-mono text-[11px] text-right">
                  <span :class="scoreToneClass(peer.score) + ' rounded px-1 py-0.5'">
                    {{ peer.score ?? "—" }}
                  </span>
                  <span :class="changeClass(peer.revenue_growth_pct)">
                    {{ fmtPct(peer.revenue_growth_pct) }}
                  </span>
                  <span :class="changeClass(peer.valuation_premium_pct)">
                    {{ fmtPct(peer.valuation_premium_pct) }}
                  </span>
                </div>
              </li>
            </ul>
            <div class="grid grid-cols-[92px_minmax(0,1fr)_auto] gap-2 text-[10px] text-ink-muted">
              <span />
              <span>{{ t("trader.research.peer_score") }}</span>
              <span class="grid grid-cols-3 gap-2 text-right">
                <span>{{ t("trader.research.score") }}</span>
                <span>{{ t("trader.research.growth") }}</span>
                <span>{{ t("trader.research.premium") }}</span>
              </span>
            </div>
          </div>

          <!-- Scenario matrix -->
          <div
            v-if="scenarioMatrix"
            class="bg-surface border border-subtle rounded-card p-4 space-y-3 lg:col-span-2"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <Target class="h-3.5 w-3.5" />
                {{ t("trader.research.scenario_matrix") }}
              </div>
              <span
                v-if="scenarioMatrix.confidence"
                :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(scenarioMatrix.confidence)]"
              >
                {{ confidenceLabel(scenarioMatrix.confidence) }}
              </span>
            </div>
            <p v-if="pickLocalized(scenarioMatrix, 'summary')" class="text-sm text-ink-primary leading-snug">
              {{ pickLocalized(scenarioMatrix, "summary") }}
            </p>
            <ul v-if="scenarioMatrix.scenarios?.length" class="space-y-3 text-xs">
              <li v-for="(s, i) in scenarioMatrix.scenarios" :key="`${s.case}-${i}`" class="space-y-1.5">
                <div class="flex items-center justify-between gap-2">
                  <span :class="['text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide', scenarioToneClass(s.case)]">
                    {{ scenarioLabel(s) }}
                  </span>
                  <span class="font-mono text-ink-primary">
                    {{ fmtPlainPct(s.probability_pct, 0) }}
                    <span :class="['ml-2', changeClass(s.implied_return_pct)]">
                      {{ fmtPct(s.implied_return_pct) }}
                    </span>
                  </span>
                </div>
                <div class="relative h-2 rounded bg-surface-muted overflow-hidden">
                  <div class="absolute inset-y-0 left-1/2 w-px bg-strong/70" />
                  <div
                    :class="[
                      'absolute inset-y-0',
                      changeBias(s.implied_return_pct) === 'down'
                        ? 'right-1/2 bg-danger'
                        : 'left-1/2 bg-success',
                    ]"
                    :style="{ width: signedBarWidth(s.implied_return_pct) + '%' }"
                  />
                </div>
                <div v-if="pickLocalized(s, 'key_driver')" class="text-[11px] text-ink-secondary leading-snug">
                  {{ pickLocalized(s, "key_driver") }}
                </div>
              </li>
            </ul>
          </div>

          <!-- Diligence questions -->
          <div
            v-if="diligenceQuestions"
            class="bg-surface border border-subtle rounded-card p-4 space-y-3"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <ClipboardList class="h-3.5 w-3.5" />
                {{ t("trader.research.diligence_questions") }}
              </div>
              <span
                v-if="diligenceQuestions.confidence"
                :class="['text-[9px] px-1 py-0.5 rounded', confidenceClass(diligenceQuestions.confidence)]"
              >
                {{ confidenceLabel(diligenceQuestions.confidence) }}
              </span>
            </div>
            <p v-if="pickLocalized(diligenceQuestions, 'summary')" class="text-sm text-ink-primary leading-snug">
              {{ pickLocalized(diligenceQuestions, "summary") }}
            </p>
            <ul v-if="diligenceQuestions.questions?.length" class="space-y-3 text-xs">
              <li v-for="(q, i) in diligenceQuestions.questions" :key="i" class="space-y-1.5">
                <div class="flex items-start justify-between gap-2">
                  <div class="flex items-start gap-1.5 min-w-0">
                    <AlertTriangle
                      v-if="q.severity === 'critical'"
                      class="h-3.5 w-3.5 text-danger mt-0.5 shrink-0"
                    />
                    <Brain
                      v-else
                      class="h-3.5 w-3.5 text-ink-muted mt-0.5 shrink-0"
                    />
                    <span class="font-medium text-ink-primary leading-snug">
                      {{ pickLocalized(q, "question") || "—" }}
                    </span>
                  </div>
                  <span :class="['text-[10px] px-1.5 py-0.5 rounded shrink-0', severityClass(q.severity)]">
                    {{ severityLabel(q.severity) }}
                  </span>
                </div>
                <div v-if="pickLocalized(q, 'why_it_matters')" class="text-[11px] text-ink-secondary leading-snug">
                  {{ pickLocalized(q, "why_it_matters") }}
                </div>
                <div v-if="pickLocalized(q, 'evidence_gap')" class="text-[11px] text-ink-muted leading-snug">
                  {{ t("trader.research.evidence_gap") }}:
                  {{ pickLocalized(q, "evidence_gap") }}
                </div>
              </li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  </section>
</template>
