<script setup>
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";

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

const analysis = ref(null);
const loading = ref(false);
const error = ref(null);
const showRisks = ref(true);

const readiness = computed(() => analysis.value?.readiness ?? null);
const gates = computed(() => readiness.value?.gates ?? []);
const blockers = computed(() => readiness.value?.approvalBlockers ?? []);
const areas = computed(() => analysis.value?.additionalAreas ?? []);
const rankedRisks = computed(() => analysis.value?.rankedRisks ?? []);

async function loadPrep() {
  if (!props.companyId) return;
  loading.value = true;
  error.value = null;
  try {
    const res = await api.getMemoAnalysis(props.companyId);
    analysis.value = res;
  } catch (err) {
    error.value = err?.message || "Failed to load IC prep";
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.companyId,
  () => {
    analysis.value = null;
    loadPrep();
  },
  { immediate: true },
);
</script>

<template>
  <div class="rounded-2xl border border-border/40 bg-surface/90 dark:bg-[#1c1c1e]/90 p-5 shadow-sm backdrop-blur-md">
    <!-- Header -->
    <div class="flex items-center justify-between pb-4 border-b border-border/30">
      <div class="flex items-center gap-2.5">
        <svg class="h-5 w-5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="m9 11 3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
        <div>
          <div class="flex items-center gap-2">
            <h3 class="font-semibold text-foreground text-sm tracking-tight">
              {{ t("research_desk.ic_prep_title") }}
            </h3>
            <span
              v-if="readiness"
              class="font-mono text-xs font-semibold px-2 py-0.5 rounded-full"
              :class="
                readiness.readyForMemo
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
              "
            >
              {{ t("research_desk.readiness_gates_score", { score: readiness.score || 0, total: readiness.total || 0 }) }}
            </span>
          </div>
          <p class="text-[11px] text-muted-foreground mt-0.5">
            {{ t("research_desk.ic_prep_subtitle") }}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-lg p-1.5 text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-colors"
          :title="t('research_desk.refresh')"
          :disabled="loading"
          @click="loadPrep"
        >
          <svg
            class="h-4 w-4"
            :class="{ 'animate-spin': loading }"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
            <path d="M21 3v5h-5" />
            <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
            <path d="M3 21v-5h5" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && !analysis" class="py-8 text-center text-xs text-muted-foreground space-y-2">
      <svg class="h-5 w-5 mx-auto animate-spin text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="2" x2="12" y2="6" />
        <line x1="12" y1="18" x2="12" y2="22" />
        <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
        <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
        <line x1="2" y1="12" x2="6" y2="12" />
        <line x1="18" y1="12" x2="22" y2="12" />
        <line x1="4.93" y1="19.07" x2="7.76" y2="16.24" />
        <line x1="16.24" y1="7.76" x2="19.07" y2="4.93" />
      </svg>
      <p>{{ t("research_desk.loading_ic_prep") }}</p>
    </div>

    <!-- Content -->
    <div v-else-if="analysis" class="mt-4 space-y-5 text-xs">
      <!-- Readiness Progress & Gates -->
      <div v-if="readiness" class="space-y-3 rounded-xl border border-border/30 bg-muted/20 p-3.5">
        <div class="flex items-center justify-between text-xs">
          <span class="font-medium text-foreground">
            {{ readiness.readyForMemo ? t("research_desk.ready_for_memo") : t("research_desk.not_ready_for_memo") }}
          </span>
          <span class="font-mono text-muted-foreground tabular-nums">
            {{ Math.round((readiness.pct || 0) * 100) }}%
          </span>
        </div>
        <div class="h-2 w-full overflow-hidden rounded-full bg-muted/40">
          <div
            class="h-full rounded-full transition-all duration-500"
            :class="readiness.readyForMemo ? 'bg-emerald-500' : 'bg-amber-500'"
            :style="{ width: `${Math.round((readiness.pct || 0) * 100)}%` }"
          />
        </div>

        <!-- Gates Grid -->
        <div v-if="gates.length" class="grid grid-cols-2 gap-2 pt-2">
          <div
            v-for="gate in gates"
            :key="gate.id"
            class="flex items-center gap-2 rounded-lg bg-surface/60 p-2 text-[11px]"
          >
            <svg
              class="h-3.5 w-3.5 shrink-0"
              :class="gate.isDone ? 'text-emerald-500' : 'text-muted-foreground/40'"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline v-if="gate.isDone" points="9 12 11 14 15 10" />
            </svg>
            <span class="truncate" :class="gate.isDone ? 'text-foreground' : 'text-muted-foreground'">
              {{ gate.label || gate.id }}
            </span>
          </div>
        </div>
      </div>

      <!-- Diligence Reviewable Areas -->
      <div v-if="areas.length" class="space-y-2">
        <h4 class="font-semibold text-muted-foreground text-[11px] uppercase tracking-wider">
          {{ t("research_desk.ic_prep_title") }}
        </h4>
        <div class="space-y-1.5">
          <div
            v-for="area in areas"
            :key="area.id"
            class="flex items-start justify-between gap-3 rounded-lg border border-border/30 bg-muted/10 p-2.5 hover:bg-muted/20 transition-colors"
          >
            <div class="space-y-0.5">
              <span class="font-medium text-foreground">{{ area.area || area.id }}</span>
              <p v-if="area.whyItMatters" class="text-[11px] text-muted-foreground">
                {{ area.whyItMatters }}
              </p>
            </div>
            <span
              class="shrink-0 text-[10px] font-mono font-medium px-2 py-0.5 rounded"
              :class="area.isOpen ? 'bg-amber-500/10 text-amber-500' : 'bg-emerald-500/10 text-emerald-500'"
            >
              {{ area.isOpen ? 'open' : (area.status || 'reviewed') }}
            </span>
          </div>
        </div>
      </div>

      <!-- Ranked Risk Cards -->
      <div v-if="rankedRisks.length" class="space-y-2">
        <div class="flex items-center justify-between">
          <h4 class="font-semibold text-muted-foreground text-[11px] uppercase tracking-wider">
            {{ t("research_desk.discrepancies_detected") }}
          </h4>
          <button
            type="button"
            class="text-[11px] text-muted-foreground hover:text-foreground"
            @click="showRisks = !showRisks"
          >
            {{ showRisks ? t("research_desk.signal_hide_formula") : t("research_desk.signal_formula") }}
          </button>
        </div>

        <div v-if="showRisks" class="space-y-1.5">
          <div
            v-for="(risk, idx) in rankedRisks.slice(0, 6)"
            :key="idx"
            class="flex items-start gap-2.5 rounded-lg border border-border/30 bg-muted/10 p-2.5"
          >
            <span
              class="shrink-0 text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
              :class="
                risk.severity === 'high'
                  ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
              "
            >
              {{ risk.severity || 'risk' }}
            </span>
            <div class="min-w-0 flex-1">
              <p class="font-medium text-foreground text-xs">{{ risk.risk || risk.title }}</p>
              <p v-if="risk.mitigant" class="text-[11px] text-muted-foreground mt-0.5">
                ↳ {{ risk.mitigant }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="py-6 text-center text-xs text-muted-foreground">
      <p>{{ t("research_desk.no_team_profiles") }}</p>
    </div>
  </div>
</template>
