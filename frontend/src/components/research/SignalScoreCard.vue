<script setup>
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { useT } from "../../i18n.js";
import { RotateCw } from "lucide-vue-next";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
  compact: {
    type: Boolean,
    default: false,
  },
});

const t = useT();

const scoreData = ref(null);
const loading = ref(false);
const error = ref(null);
const expanded = ref(false);

const score = computed(() => scoreData.value?.score ?? null);

const isInsufficient = computed(() => {
  return scoreData.value?.is_insufficient ?? (score.value == null);
});

const colorClass = computed(() => {
  if (score.value == null || isInsufficient.value) return "text-neutral-400";
  if (score.value >= 70) return "text-emerald-400";
  if (score.value >= 40) return "text-amber-400";
  return "text-rose-400";
});

const strokeColor = computed(() => {
  if (score.value == null || isInsufficient.value) return "rgba(255, 255, 255, 0.15)";
  if (score.value >= 70) return "#34c759";
  if (score.value >= 40) return "#ff9500";
  return "#ff3b30";
});

const circumference = 2 * Math.PI * 18; // r=18 for 44px
const strokeDashoffset = computed(() => {
  if (score.value == null || isInsufficient.value) return circumference;
  const clamped = Math.max(0, Math.min(100, score.value));
  return circumference - (clamped / 100) * circumference;
});

const coverageSubtitle = computed(() => {
  if (!scoreData.value) return loading.value ? t("workspace.loading") : "Loading…";
  if (scoreData.value.is_insufficient) {
    const covered = (scoreData.value.components || []).filter((c) => c.available).length;
    const total = (scoreData.value.components || []).length;
    return `Insufficient data · ${covered} of ${total}`;
  }
  return (scoreData.value.coverage || "").replace(" have data", " with data") || "2 of 6 components with data";
});

const formulaText = computed(() => {
  return (
    scoreData.value?.formula ||
    "score = Σ points ÷ Σ max of components with data × 100, shown only with ≥2 components and ≥35 max points"
  );
});

async function loadSignalScore() {
  if (!props.companyId) return;
  loading.value = true;
  error.value = null;
  try {
    const res = await api.getSignalScore(props.companyId);
    scoreData.value = res;
  } catch (err) {
    error.value = err?.message || "Failed to load signal score";
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.companyId,
  () => {
    loadSignalScore();
  },
  { immediate: true },
);
</script>

<template>
  <div class="rounded-xl border border-white/[0.08] bg-[#1c1c1f] p-3 shadow-xs transition-all text-white">
    <div class="flex items-center gap-3">
      <!-- Compact Circular SVG Gauge (Matching MacSignalScoreView.swift 44-52px) -->
      <div class="relative flex shrink-0 items-center justify-center w-[44px] h-[44px]">
        <svg class="h-full w-full -rotate-90 transform" viewBox="0 0 44 44">
          <circle
            cx="22"
            cy="22"
            r="18"
            fill="transparent"
            stroke="rgba(255, 255, 255, 0.12)"
            stroke-width="3.5"
          />
          <circle
            cx="22"
            cy="22"
            r="18"
            fill="transparent"
            :stroke="strokeColor"
            stroke-width="3.5"
            stroke-linecap="round"
            :stroke-dasharray="circumference"
            :stroke-dashoffset="strokeDashoffset"
            class="transition-all duration-700 ease-out"
          />
        </svg>
        <span
          class="absolute font-bold tracking-tight tabular-nums select-none"
          :class="[compact ? 'text-xs' : 'text-sm', colorClass]"
        >
          {{ isInsufficient || score == null ? "—" : score }}
        </span>
      </div>

      <!-- Title, Coverage Subtitle & Formula (Mac headline / caption typography) -->
      <div class="flex-1 min-w-0 flex flex-col justify-center">
        <h3 class="text-sm font-semibold tracking-tight text-white leading-tight">
          {{ t("research_desk.signal_score") }}
        </h3>
        <p class="text-xs text-neutral-400 leading-tight mt-0.5 truncate">
          {{ coverageSubtitle }}
        </p>
        <p v-if="!compact" class="text-[10px] font-mono text-neutral-500 leading-tight mt-0.5 truncate">
          {{ formulaText }}
        </p>
      </div>

      <!-- Right Action Controls: Formula toggle and Refresh icon button -->
      <div class="flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          class="rounded border border-white/10 bg-white/5 hover:bg-white/10 px-2 py-0.5 text-[11px] font-medium text-neutral-200 transition-colors shadow-2xs"
          @click="expanded = !expanded"
        >
          {{ expanded ? t("research_desk.signal_hide_formula") : t("research_desk.signal_formula") }}
        </button>

        <button
          type="button"
          class="flex h-6 w-6 items-center justify-center rounded text-neutral-400 hover:text-white transition-colors"
          :title="t('research_desk.refresh')"
          :disabled="loading"
          @click="loadSignalScore"
        >
          <RotateCw class="h-3 w-3" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </div>

    <!-- Collapsible Component Breakdown Table (MacSignalScoreView.swift:485-505) -->
    <div
      v-if="expanded && scoreData?.components"
      class="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2 space-y-1.5 divide-y divide-white/[0.04] text-xs"
    >
      <div
        v-for="c in scoreData.components"
        :key="c.name"
        class="flex flex-wrap items-start justify-between gap-2 pt-1.5 first:pt-0"
      >
        <div class="w-28 shrink-0 font-medium text-neutral-200 truncate">
          {{ c.name }}
        </div>

        <div class="w-28 shrink-0 font-mono text-neutral-400">
          <span :class="c.available ? 'text-white font-semibold' : 'text-neutral-500'">
            {{ c.available ? `${Number(c.points || 0).toFixed(1)} / ${c.max}` : `not scored · ${c.max} max` }}
          </span>
        </div>

        <div class="flex-1 min-w-[140px] text-[11px]">
          <div class="text-neutral-400">{{ c.formula }}</div>
          <div v-if="c.basis" class="text-neutral-500 text-[10px]">{{ c.basis }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
