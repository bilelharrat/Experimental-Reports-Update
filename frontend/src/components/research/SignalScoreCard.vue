<script setup>
// Web twin of MacSignalScoreView (MacFirmViews.swift): the 52pt ring gauge
// with 5pt round-capped stroke, dsHeadline title, coverage caption, tertiary
// formula line, and the expandable component breakdown table.
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

// score >= 70 → green, >= 40 → orange, else red; secondary while unknown.
const strokeColor = computed(() => {
  if (score.value == null) return "var(--mac-secondary)";
  if (score.value >= 70) return "var(--mac-green)";
  if (score.value >= 40) return "var(--mac-orange)";
  return "var(--mac-red)";
});

const gaugeSize = computed(() => (props.compact ? 40 : 52));
const radius = computed(() => (gaugeSize.value - 5) / 2);
const circumference = computed(() => 2 * Math.PI * radius.value);
const strokeDashoffset = computed(() => {
  if (score.value == null) return circumference.value;
  const clamped = Math.max(0, Math.min(100, score.value));
  return circumference.value - (clamped / 100) * circumference.value;
});

const coverageSubtitle = computed(() => {
  if (!scoreData.value) return t("research_desk.loading_ellipsis");
  if (scoreData.value.is_insufficient) {
    const covered = (scoreData.value.components || []).filter((c) => c.available).length;
    const total = (scoreData.value.components || []).length;
    return `Insufficient data · ${covered} of ${total}`;
  }
  return (scoreData.value.coverage || "").replace(" have data", " with data");
});

const formulaText = computed(() => scoreData.value?.formula || "");

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
  <div class="mac-card flex flex-col gap-2" :class="compact ? 'p-2' : 'p-3'">
    <div class="flex items-center gap-2.5">
      <!-- Ring gauge: Circle stroke 5pt, secondary 15% track, round cap -->
      <div
        class="relative flex shrink-0 items-center justify-center"
        :style="{ width: `${gaugeSize}px`, height: `${gaugeSize}px` }"
      >
        <svg class="h-full w-full -rotate-90 transform" :viewBox="`0 0 ${gaugeSize} ${gaugeSize}`">
          <circle
            :cx="gaugeSize / 2"
            :cy="gaugeSize / 2"
            :r="radius"
            fill="transparent"
            stroke="color-mix(in srgb, var(--mac-secondary) 15%, transparent)"
            stroke-width="5"
          />
          <circle
            :cx="gaugeSize / 2"
            :cy="gaugeSize / 2"
            :r="radius"
            fill="transparent"
            :stroke="strokeColor"
            stroke-width="5"
            stroke-linecap="round"
            :stroke-dasharray="circumference"
            :stroke-dashoffset="strokeDashoffset"
            style="transition: stroke-dashoffset 0.7s ease-out, stroke 0.3s ease"
          />
        </svg>
        <span
          class="mac-mono absolute select-none font-bold"
          :style="{ fontSize: compact ? '12px' : '15px' }"
        >
          {{ score == null ? "—" : score }}
        </span>
      </div>

      <!-- Signal score · coverage · formula -->
      <div class="flex min-w-0 flex-1 flex-col justify-center gap-0.5">
        <h3 :class="compact ? 'mac-t-subhead' : 'mac-t-headline'">
          {{ t("research_desk.signal_score") }}
        </h3>
        <p class="mac-t-caption mac-c-secondary line-clamp-2">
          {{ coverageSubtitle }}
        </p>
        <p v-if="!compact && formulaText" class="mac-t-caption mac-c-tertiary truncate">
          {{ formulaText }}
        </p>
      </div>

      <!-- "Formula" toggle (mini) + refresh (plain mini) -->
      <div class="flex shrink-0 items-center gap-1.5">
        <button type="button" class="mac-btn mac-btn--mini" @click="expanded = !expanded">
          {{ expanded ? t("research_desk.signal_hide_formula") : t("research_desk.signal_formula") }}
        </button>

        <button
          type="button"
          class="mac-btn mac-btn--mini mac-btn--plain"
          :title="t('research_desk.refresh')"
          :disabled="loading"
          @click="loadSignalScore"
        >
          <RotateCw class="h-3 w-3" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </div>

    <!-- Component breakdown rows on a 4% tint, hairline-divided -->
    <div v-if="expanded && scoreData?.components" class="overflow-hidden rounded-md"
      style="background: color-mix(in srgb, var(--mac-secondary) 4%, transparent)"
    >
      <div
        v-for="(c, idx) in scoreData.components"
        :key="c.name"
        class="flex items-start gap-2 px-2 py-[5px]"
        :class="idx > 0 ? 'mac-hairline-t' : ''"
      >
        <span class="mac-t-caption10 w-[110px] shrink-0 truncate font-semibold">{{ c.name }}</span>
        <span
          class="mac-t-caption10 mac-mono w-[120px] shrink-0"
          :class="c.available ? '' : 'mac-c-secondary'"
        >
          {{ c.available ? `${Number(c.points || 0).toFixed(1)} / ${c.max}` : `not scored · ${c.max} max` }}
        </span>
        <span class="flex min-w-0 flex-col gap-px">
          <span class="mac-t-caption10 mac-c-secondary">{{ c.formula }}</span>
          <span v-if="c.basis" class="mac-t-caption10 mac-c-tertiary">{{ c.basis }}</span>
        </span>
      </div>
    </div>
  </div>
</template>
