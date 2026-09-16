<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useT } from "../../i18n.js";
import api from "../../api.js";
import { formatCompactNumber } from "../../formatters.js";
import { RotateCw, ExternalLink, Layers } from "lucide-vue-next";

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
onMounted(loadProfile);

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

const privateSide = computed(() => {
  const pr = profile.value?.private || profile.value?.private_facts;
  if (!pr && !props.company?.funding_round && !props.company?.metrics) return null;

  const pos = pr?.position || {};
  const kpi = pr?.latest_kpi || props.company?.metrics || {};
  const mark = pr?.latest_mark;
  const moic = pr?.moic;

  const round = pos.round || props.company?.funding_round;
  const invested = pos.invested_usd ? `$${formatCompactNumber(pos.invested_usd)}` : null;
  const positionStr = [round, invested].filter(Boolean).join(" · ") || "—";
  const ownStr = pos.ownership_pct != null ? `${Number(pos.ownership_pct).toFixed(1)}%` : "—";

  const arrVal = kpi.arr_usd ?? kpi.arr ?? kpi.annual_recurring_revenue;
  const arrStr = arrVal != null ? (typeof arrVal === "number" ? `$${formatCompactNumber(arrVal)}` : arrVal) : "—";

  const runwayMonths = kpi.runway_months ?? kpi.runway;
  const runwayStr = runwayMonths != null ? `${runwayMonths} mo` : "—";
  const isRunwayTight = runwayMonths != null && Number(runwayMonths) < 9;

  const markVal = mark?.value_usd ?? pr?.mark ?? props.company?.valuation;
  const markStr = markVal != null ? (typeof markVal === "number" ? `$${formatCompactNumber(markVal)}` : markVal) : null;
  const moicStr = moic != null ? `${Number(moic).toFixed(2)}x` : null;
  const markMoicStr = [markStr, moicStr].filter(Boolean).join(" · ") || "—";

  return {
    position: positionStr,
    ownership: ownStr,
    arr: arrStr,
    runway: runwayStr,
    isRunwayTight,
    markMoic: markMoicStr,
  };
});

const processSide = computed(() => {
  const p = profile.value || {};
  const pipeline = p.pipeline || {};
  const proc = p.process_facts || {};
  const stage = pipeline.stage ?? proc.stage ?? props.company?.deal_stage ?? "Sourced";

  const thesisFit = p.thesis_fit?.score != null ? `${p.thesis_fit.score}%` : (p.thesis_fit?.fit || "0%");

  let verdict = "—";
  if (p.latest_decision?.verdict) {
    verdict = p.latest_decision.verdict.toUpperCase();
  } else if (p.decisions?.length > 0) {
    verdict = p.decisions[0].verdict.toUpperCase();
  }

  const meetings = p.ic?.meeting_count ?? p.ic_meetings?.length ?? 0;
  const refs = p.ic?.reference_calls ?? p.reference_calls?.length ?? 0;
  const isMeetingOpen = Boolean(p.ic?.open_meeting);
  const icStr = isMeetingOpen ? "Meeting open" : `${meetings} meetings · ${refs} refs`;

  const counts = p.counts || {};
  const files = counts.files ?? p.files_count ?? 0;
  const transcripts = counts.transcripts ?? p.transcripts_count ?? 0;
  const openComments = counts.open_comments ?? p.open_comments_count ?? 0;
  const onFileStr = `${files} files · ${transcripts} transcripts · ${openComments} open comments`;

  return {
    stage,
    thesisFit,
    verdict,
    ic: icStr,
    onFile: onFileStr,
  };
});
</script>

<template>
  <div class="rounded-xl border border-white/[0.08] bg-[#1c1c1f] p-3.5 shadow-xs transition-all text-white">
    <!-- Header (MacUnifiedProfileView.swift:15-24) -->
    <div class="flex items-center justify-between pb-3 border-b border-white/[0.06]">
      <div class="flex items-center gap-2">
        <Layers class="h-4 w-4 text-[#0a84ff]" />
        <span class="font-semibold text-white text-xs">
          {{ t("research_desk.profile_title") }}
        </span>
      </div>

      <div class="flex items-center gap-2">
        <!-- MacStatusPill (Public / Private) -->
        <span
          class="rounded-full px-2.5 py-0.5 text-xs font-semibold tracking-tight inline-flex items-center gap-1"
          :class="isPublic ? 'bg-blue-500/15 text-blue-400' : 'bg-purple-500/15 text-purple-400'"
        >
          <span>{{ isPublic ? t("research_desk.public_tag") : t("research_desk.private_tag") }}</span>
          <ExternalLink v-if="isPublic && company?.web_url" class="h-3 w-3 opacity-80" />
        </span>

        <button
          type="button"
          class="flex h-6 w-6 items-center justify-center rounded text-neutral-400 hover:text-white transition-colors"
          :title="t('research_desk.refresh')"
          :disabled="loading"
          @click="loadProfile"
        >
          <RotateCw class="h-3 w-3" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </div>

    <!-- 3-Column HIG Data Grid (MacUnifiedProfileView.swift:26-61) -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-5 pt-3 text-xs">
      <!-- Column 1: Public -->
      <div class="space-y-1.5">
        <div class="font-semibold text-neutral-400 text-[11px] uppercase tracking-wider mb-2">
          {{ t("research_desk.public_upper") }}
        </div>

        <div v-if="publicSide.lastPrice != null" class="space-y-1.5">
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.ticker") }}</span>
            <span class="font-mono text-white text-[11px]">{{ publicSide.ticker || "—" }}</span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.last_price") }}</span>
            <span
              class="font-mono text-[11px] font-semibold"
              :class="(publicSide.changePct1d ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'"
            >
              ${{ publicSide.lastPrice.toFixed(2) }}
            </span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">1D</span>
            <span
              class="font-mono text-[11px]"
              :class="(publicSide.changePct1d ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'"
            >
              {{ publicSide.changePct1d != null ? `${publicSide.changePct1d >= 0 ? '+' : ''}${publicSide.changePct1d.toFixed(2)}%` : "—" }}
            </span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.market_cap") }}</span>
            <span class="font-mono text-neutral-200 text-[11px]">{{ publicSide.marketCap }}</span>
          </div>
        </div>
        <div v-else class="text-[11px] text-neutral-500 italic pt-1">
          {{ isPublic ? t("research_desk.quote_unavailable") : t("research_desk.no_public_listing") }}
        </div>
      </div>

      <!-- Column 2: Private -->
      <div class="space-y-1.5">
        <div class="font-semibold text-neutral-400 text-[11px] uppercase tracking-wider mb-2">
          {{ t("research_desk.private_upper") }}
        </div>

        <div v-if="privateSide" class="space-y-1.5">
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.position") }}</span>
            <span class="font-mono text-white text-[11px] truncate">{{ privateSide.position }}</span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.ownership") }}</span>
            <span class="font-mono text-white text-[11px]">{{ privateSide.ownership }}</span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">ARR</span>
            <span class="font-mono text-white text-[11px]">{{ privateSide.arr }}</span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.runway") }}</span>
            <span
              class="font-mono text-[11px]"
              :class="privateSide.isRunwayTight ? 'text-rose-400 font-semibold' : 'text-white'"
            >
              {{ privateSide.runway }}
            </span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.mark_moic") }}</span>
            <span class="font-mono text-neutral-200 text-[11px] truncate">{{ privateSide.markMoic }}</span>
          </div>
        </div>
        <div v-else class="text-[11px] text-neutral-500 italic pt-1">
          {{ t("research_desk.no_position") }}
        </div>
      </div>

      <!-- Column 3: Process -->
      <div class="space-y-1.5">
        <div class="font-semibold text-neutral-400 text-[11px] uppercase tracking-wider mb-2">
          {{ t("research_desk.process_upper") }}
        </div>

        <div class="space-y-1.5">
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.stage") }}</span>
            <span class="font-medium text-white text-[11px]">{{ processSide.stage }}</span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.thesis_fit") }}</span>
            <span class="font-mono text-[#0a84ff] text-[11px] font-semibold">{{ processSide.thesisFit }}</span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.decision") }}</span>
            <span
              class="font-mono font-semibold text-[11px]"
              :class="
                processSide.verdict.toLowerCase().includes('invest')
                  ? 'text-emerald-400'
                  : processSide.verdict.toLowerCase().includes('pass')
                  ? 'text-rose-400'
                  : 'text-neutral-300'
              "
            >
              {{ processSide.verdict }}
            </span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">IC</span>
            <span class="text-neutral-300 text-[11px] truncate">{{ processSide.ic }}</span>
          </div>
          <div class="flex items-center text-xs">
            <span class="text-neutral-400 text-[11px] w-[74px] shrink-0">{{ t("research_desk.on_file") }}</span>
            <span class="text-neutral-400 text-[10px] truncate">{{ processSide.onFile }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Description (Max 2 lines, MacUnifiedProfileView.swift:63) -->
    <div
      v-if="profile?.description || company?.description"
      class="mt-3 pt-2.5 border-t border-white/[0.06] text-xs text-neutral-400 line-clamp-2 leading-relaxed"
    >
      {{ profile?.description || company?.description }}
    </div>
  </div>
</template>
