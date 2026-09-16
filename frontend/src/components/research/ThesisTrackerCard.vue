<script setup>
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
});

const analysis = ref(null);
const evidence = ref(null);
const loading = ref(false);

const claims = computed(() => {
  return analysis.value?.thesis_spine ?? analysis.value?.thesisSpine ?? [];
});

async function loadThesis() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    const [analysisRes, evidenceRes] = await Promise.allSettled([
      api.getMemoAnalysis(props.companyId),
      api.getEvidence(props.companyId),
    ]);
    if (analysisRes.status === "fulfilled") {
      analysis.value = analysisRes.value;
    }
    if (evidenceRes.status === "fulfilled") {
      evidence.value = evidenceRes.value;
    }
  } finally {
    loading.value = false;
  }
}

function statusColorClass(status) {
  if (status === "supported") return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
  if (status === "contradicted") return "bg-rose-500/10 text-rose-600 dark:text-rose-400";
  if (status === "mixed") return "bg-amber-500/10 text-amber-600 dark:text-amber-400";
  return "bg-muted/30 text-muted-foreground";
}

watch(
  () => props.companyId,
  () => {
    loadThesis();
  },
  { immediate: true },
);
</script>

<template>
  <div class="rounded-2xl border border-border/40 bg-surface/90 dark:bg-[#1c1c1e]/90 p-5 shadow-sm backdrop-blur-md">
    <!-- Header -->
    <div class="flex items-center justify-between pb-3 border-b border-border/30">
      <div class="flex items-center gap-2.5">
        <svg class="h-5 w-5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <polygon points="12 8 8 12 12 16 16 12 12 8" />
        </svg>
        <h3 class="font-semibold text-foreground text-sm tracking-tight">
          {{ t("research_desk.thesis_tracker_title") }}
        </h3>
      </div>

      <button
        type="button"
        class="rounded-lg p-1.5 text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-colors"
        :title="t('research_desk.refresh')"
        :disabled="loading"
        @click="loadThesis"
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

    <!-- Body -->
    <div class="pt-4 space-y-3 text-xs">
      <div v-if="claims.length" class="space-y-2.5">
        <div
          v-for="(row, idx) in claims"
          :key="idx"
          class="rounded-xl border border-border/30 bg-muted/10 p-3 space-y-2"
        >
          <div class="flex items-start justify-between gap-3">
            <p class="font-medium text-foreground text-xs leading-snug">
              {{ row.claim || row.statement }}
            </p>
            <span
              class="shrink-0 rounded px-2 py-0.5 text-[10px] font-semibold uppercase"
              :class="statusColorClass(row.evidence_status || row.evidenceStatus)"
            >
              {{ row.evidence_status || row.evidenceStatus || "unverified" }}
            </span>
          </div>

          <div v-if="row.latest_news" class="flex items-center gap-2 text-[11px] text-muted-foreground pt-1 border-t border-border/20">
            <svg class="h-3.5 w-3.5 text-accent shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2" />
            </svg>
            <span class="truncate">{{ row.latest_news.title }}</span>
          </div>
        </div>
      </div>

      <div v-else class="py-6 text-center text-muted-foreground text-xs">
        {{ t("research_desk.no_thesis_spine") }}
      </div>
    </div>
  </div>
</template>
