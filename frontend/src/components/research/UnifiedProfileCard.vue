<script setup>
// Web twin of MacUnifiedProfileView (MacBatchEViews.swift): the unified
// public/private/process profile card. 12pt card padding, Label header at
// 11/600, three plain-case columns of 74pt-label facts at 10pt mono.
import { ref, computed, watch } from "vue";
import { useT } from "../../i18n.js";
import api from "../../api.js";
import { formatCompactNumber } from "../../formatters.js";
import { inferredMetricSourceKey } from "../../companyMetrics.js";
import { RotateCw, Layers } from "lucide-vue-next";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
  company: {
    type: Object,
    default: () => ({}),
  },
});

const t = useT();

const loading = ref(false);
const profile = ref(null);
const loadAttempted = ref(false);

async function loadProfile() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    const res = await api.getCompanyProfile(props.companyId);
    profile.value = res;
  } catch {
    profile.value = null;
  } finally {
    loading.value = false;
    loadAttempted.value = true;
  }
}

watch(() => props.companyId, loadProfile, { immediate: true });

const isPublic = computed(() => {
  if (profile.value?.is_public !== undefined) return Boolean(profile.value.is_public);
  return Boolean(props.company?.ticker);
});

const publicSide = computed(() => {
  const p = profile.value?.public || profile.value?.public_facts || {};
  const quote = profile.value?.quote || {};
  const ticker = p.ticker || quote.symbol || props.company?.ticker || "";
  const lastPrice = p.last_price ?? quote.regularMarketPrice ?? quote.price;
  const changePct1d = p.change_pct_1d ?? quote.regularMarketChangePercent ?? quote.change_percent;
  const marketCap = p.market_cap ?? quote.marketCap ?? props.company?.market_cap;

  return {
    ticker,
    lastPrice: lastPrice != null ? Number(lastPrice) : null,
    changePct1d: changePct1d != null ? Number(changePct1d) : null,
    marketCap: marketCap != null ? (typeof marketCap === "number" ? `$${formatCompactNumber(marketCap)}` : marketCap) : "—",
  };
});

// "2026-06-13" → "2026-06"; a bare year ("2030") or free text stays as is.
function asOfLabel(asOf) {
  const raw = String(asOf || "").trim();
  return /^\d{4}-\d{2}-\d{2}/.test(raw) ? raw.slice(0, 7) : raw;
}

// The hover line under a reported figure: label · as of · where it came
// from. A known source class reads in the UI language (the ZaiNar demo
// values say they are demo values, in Chinese too).
function reportedTitle(fact) {
  if (!fact) return "";
  const sourceKey = inferredMetricSourceKey(fact.source_class);
  return [
    fact.label,
    fact.as_of && t("company.metric_as_of", { when: fact.as_of }),
    sourceKey ? t(sourceKey) : fact.source_class,
  ]
    .filter(Boolean)
    .join(" · ");
}

const privateSide = computed(() => {
  const pr = profile.value?.private || profile.value?.private_facts;
  // The company record's own figures (the rows the memo snapshot quotes),
  // used when there is no portfolio KPI for them.
  const reported = profile.value?.reported || {};
  if (!pr && !props.company?.funding_round && !props.company?.metrics && !Object.keys(reported).length) {
    return null;
  }

  const pos = pr?.position || {};
  const kpi = pr?.latest_kpi || props.company?.metrics || {};
  const mark = pr?.latest_mark;
  const moic = pr?.moic;

  const round = pos.round || props.company?.funding_round;
  const invested = pos.invested_usd ? `$${formatCompactNumber(pos.invested_usd)}` : null;
  const positionStr = [round, invested].filter(Boolean).join(" · ") || "—";
  const ownStr = pos.ownership_pct != null ? `${Number(pos.ownership_pct).toFixed(1)}%` : "—";

  const arrVal = kpi.arr_usd ?? kpi.arr ?? kpi.annual_recurring_revenue;
  const arrFact = arrVal == null ? reported.arr : null;
  const arrStr =
    arrVal != null
      ? (typeof arrVal === "number" ? `$${formatCompactNumber(arrVal)}` : arrVal)
      : arrFact?.value || "—";

  const runwayMonths = kpi.runway_months ?? kpi.runway;
  const runwayFact = runwayMonths == null ? reported.runway : null;
  const runwayStr =
    runwayMonths != null ? `${Math.round(Number(runwayMonths))} mo` : runwayFact?.value || "—";
  const isRunwayTight = runwayMonths != null && Number(runwayMonths) < 9;

  const markVal = mark?.value_usd ?? pr?.mark ?? props.company?.valuation;
  const markStr = markVal != null ? (typeof markVal === "number" ? `$${formatCompactNumber(markVal)}` : markVal) : null;
  const moicStr = moic != null ? `${Number(moic).toFixed(2)}x` : null;
  const markMoicStr = [markStr, moicStr].filter(Boolean).join(" · ") || "—";

  return {
    position: positionStr,
    ownership: ownStr,
    arr: arrStr,
    arrAsOf: asOfLabel(arrFact?.as_of),
    arrTitle: reportedTitle(arrFact),
    runway: runwayStr,
    runwayAsOf: asOfLabel(runwayFact?.as_of),
    runwayTitle: reportedTitle(runwayFact),
    isRunwayTight,
    markMoic: markMoicStr,
  };
});

function capitalize(v) {
  const s = String(v || "");
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

// A listed company is not a startup deal. Unless the firm holds a position
// in it, the middle column shows how the market values it — P/E, EPS, the
// 52-week range, yield — instead of Position / ARR / Runway / Mark, which
// read "—" for every public name. The quote already carries these fields.
const holdsPosition = computed(() => Boolean(profile.value?.private));
const showMarketColumn = computed(() => isPublic.value && !holdsPosition.value);

function fmtNumber(value, digits = 2) {
  return value == null || !Number.isFinite(Number(value)) ? null : Number(value).toFixed(digits);
}

const marketSide = computed(() => {
  const q = profile.value?.public || {};
  const low = fmtNumber(q.fifty_two_week_low);
  const high = fmtNumber(q.fifty_two_week_high);
  const yieldPct = q.dividend_yield != null ? fmtNumber(Number(q.dividend_yield) * 100) : null;
  return {
    pe: fmtNumber(q.pe_ratio, 1) ?? "—",
    eps: q.eps != null ? `$${fmtNumber(q.eps)}` : "—",
    range: low && high ? `$${low} – $${high}` : "—",
    dividendYield: yieldPct != null ? `${yieldPct}%` : "—",
  };
});

const processSide = computed(() => {
  const p = profile.value || {};
  const pipeline = p.pipeline || {};
  const proc = p.process_facts || {};
  const stage = pipeline.stage ?? proc.stage ?? props.company?.deal_stage ?? "Sourced";

  const thesisFit = p.thesis_fit?.score != null
    ? `${p.thesis_fit.score}%`
    : capitalize(p.thesis_fit?.fit || "—");

  let verdict = "—";
  if (p.latest_decision?.verdict) {
    verdict = p.latest_decision.verdict;
  } else if (p.decisions?.length > 0) {
    verdict = p.decisions[0].verdict;
  }

  const meetings = p.ic?.meeting_count ?? p.ic_meetings?.length ?? 0;
  const refs = p.ic?.reference_calls ?? p.reference_calls?.length ?? 0;
  const isMeetingOpen = Boolean(p.ic?.open_meeting);
  const icStr = `${isMeetingOpen ? "Meeting open" : `${meetings} meetings`} · ${refs} refs`;

  const counts = p.counts || {};
  const files = counts.files ?? p.files_count ?? 0;
  const transcripts = counts.transcripts ?? p.transcripts_count ?? 0;
  const openComments = counts.open_comments ?? p.open_comments_count ?? 0;
  const onFileStr = `${files} files · ${transcripts} transcripts · ${openComments} open comments`;

  return {
    stage,
    thesisFit,
    verdict: capitalize(verdict),
    verdictTone:
      String(verdict).toLowerCase() === "invest"
        ? "var(--mac-green)"
        : String(verdict).toLowerCase() === "pass"
          ? "var(--mac-red)"
          : "var(--mac-label)",
    ic: icStr,
    onFile: onFileStr,
  };
});
</script>

<template>
  <div class="mac-card flex flex-col gap-2.5 p-3">
    <!-- Label("Profile", square.on.square.dashed) · pill · refresh -->
    <div class="flex items-center gap-2">
      <Layers class="mac-c-accent h-3.5 w-3.5" />
      <span class="mac-t-subheadline" style="font-weight: 600">{{ t("research_desk.profile_title") }}</span>
      <span class="flex-1" />
      <span
        v-if="profile"
        class="mac-status-pill"
        :style="{ '--tint': isPublic ? 'var(--mac-blue)' : 'var(--mac-purple)' }"
      >
        {{ isPublic ? t("research_desk.public_tag") : t("research_desk.private_tag") }}
      </span>
      <button
        type="button"
        class="mac-btn mac-btn--mini mac-btn--plain"
        :title="t('research_desk.refresh')"
        :disabled="loading"
        @click="loadProfile"
      >
        <RotateCw class="h-3 w-3" :class="{ 'animate-spin': loading }" />
      </button>
    </div>

    <template v-if="profile">
      <!-- Three fact columns: Public · Private · Process -->
      <div class="grid grid-cols-1 gap-3.5 md:grid-cols-3">
        <!-- Public -->
        <div class="flex min-w-0 flex-col gap-1">
          <span class="mac-t-label mac-c-secondary">{{ t("research_desk.public_quote") }}</span>
          <template v-if="publicSide.lastPrice != null">
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.ticker") }}</span>
              <span class="mac-t-caption10 mac-mono truncate">{{ publicSide.ticker || "—" }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.last_price") }}</span>
              <span
                class="mac-t-caption10 mac-mono truncate"
                :style="{ color: (publicSide.changePct1d ?? 0) >= 0 ? 'var(--mac-green)' : 'var(--mac-red)' }"
              >
                ${{ publicSide.lastPrice.toFixed(2) }}
              </span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">1D</span>
              <span class="mac-t-caption10 mac-mono truncate">
                {{ publicSide.changePct1d != null ? `${publicSide.changePct1d >= 0 ? "+" : ""}${publicSide.changePct1d.toFixed(2)}%` : "—" }}
              </span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.market_cap") }}</span>
              <span class="mac-t-caption10 mac-mono truncate">{{ publicSide.marketCap }}</span>
            </div>
          </template>
          <span v-else class="mac-t-caption10 mac-c-secondary">
            {{ isPublic ? t("research_desk.quote_unavailable") : t("research_desk.no_public_listing") }}
          </span>
        </div>

        <!-- Market (listed company, no position held) -->
        <div v-if="showMarketColumn" class="flex min-w-0 flex-col gap-1" data-testid="profile-market">
          <span class="mac-t-label mac-c-secondary">{{ t("research_desk.market_data") }}</span>
          <div class="flex items-center gap-1.5">
            <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">P/E</span>
            <span class="mac-t-caption10 mac-mono truncate">{{ marketSide.pe }}</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">EPS</span>
            <span class="mac-t-caption10 mac-mono truncate">{{ marketSide.eps }}</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.range_52w") }}</span>
            <span class="mac-t-caption10 mac-mono truncate">{{ marketSide.range }}</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.dividend_yield") }}</span>
            <span class="mac-t-caption10 mac-mono truncate">{{ marketSide.dividendYield }}</span>
          </div>
        </div>

        <!-- Private -->
        <div v-else class="flex min-w-0 flex-col gap-1">
          <span class="mac-t-label mac-c-secondary">{{ t("research_desk.private_data") }}</span>
          <template v-if="privateSide">
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.position") }}</span>
              <span class="mac-t-caption10 mac-mono truncate">{{ privateSide.position }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.ownership") }}</span>
              <span class="mac-t-caption10 mac-mono truncate">{{ privateSide.ownership }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">ARR</span>
              <span class="mac-t-caption10 mac-mono truncate" :title="privateSide.arrTitle || null" data-testid="profile-arr">{{ privateSide.arr }}</span>
              <span v-if="privateSide.arrAsOf" class="mac-t-caption10 mac-c-tertiary shrink-0">{{ privateSide.arrAsOf }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.runway") }}</span>
              <span
                class="mac-t-caption10 mac-mono truncate"
                :style="privateSide.isRunwayTight ? { color: 'var(--mac-red)' } : {}"
              >
                {{ privateSide.runway }}
              </span>
              <span v-if="privateSide.runwayAsOf" class="mac-t-caption10 mac-c-tertiary shrink-0" :title="privateSide.runwayTitle || null">{{ privateSide.runwayAsOf }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.mark_moic") }}</span>
              <span class="mac-t-caption10 mac-mono truncate">{{ privateSide.markMoic }}</span>
            </div>
          </template>
          <span v-else class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.no_position") }}</span>
        </div>

        <!-- Process -->
        <div class="flex min-w-0 flex-col gap-1">
          <span class="mac-t-label mac-c-secondary">{{ t("research_desk.process_status") }}</span>
          <!-- Deal stage and VC thesis fit mean nothing for a listed name. -->
          <template v-if="!isPublic">
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.stage") }}</span>
              <span class="mac-t-caption10 mac-mono truncate">{{ processSide.stage }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.thesis_fit") }}</span>
              <span class="mac-t-caption10 mac-mono truncate">{{ processSide.thesisFit }}</span>
            </div>
          </template>
          <div class="flex items-center gap-1.5">
            <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.decision") }}</span>
            <span class="mac-t-caption10 mac-mono truncate" :style="{ color: processSide.verdictTone }">
              {{ processSide.verdict }}
            </span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">IC</span>
            <span class="mac-t-caption10 mac-mono truncate">{{ processSide.ic }}</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="mac-t-caption10 mac-c-secondary w-[74px] shrink-0">{{ t("research_desk.on_file") }}</span>
            <span class="mac-t-caption10 mac-mono truncate">{{ processSide.onFile }}</span>
          </div>
        </div>
      </div>

      <!-- Description, two lines max -->
      <p
        v-if="profile?.description || company?.description"
        class="mac-t-caption10 mac-c-secondary line-clamp-2"
      >
        {{ profile?.description || company?.description }}
      </p>
    </template>

    <!-- Unavailable / loading -->
    <div v-else-if="loadAttempted" class="flex items-center gap-2">
      <span class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.profile_unavailable") }}</span>
      <button type="button" class="mac-btn mac-btn--mini" @click="loadProfile">
        {{ t("research_desk.retry") }}
      </button>
    </div>
    <div v-else class="py-1"><span class="mac-spinner" /></div>
  </div>
</template>
