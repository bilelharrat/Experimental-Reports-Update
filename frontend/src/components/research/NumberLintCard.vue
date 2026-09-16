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

const lint = ref(null);
const loading = ref(false);
const expanded = ref(false);

const hasMemo = computed(() => lint.value?.memo_package != null || lint.value?.memoPackage != null);
const supported = computed(() => lint.value?.supported ?? 0);
const checked = computed(() => lint.value?.checked ?? 0);
const unsupported = computed(() => lint.value?.unsupported ?? 0);
const findings = computed(() => lint.value?.findings ?? []);

async function loadLint() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    const res = await api.getMemoAnalysis(props.companyId);
    lint.value = res?.numbers_lint ?? res?.numberLint ?? null;
  } catch (err) {
    console.error("Failed to load numbers lint", err);
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.companyId,
  () => {
    loadLint();
  },
  { immediate: true },
);
</script>

<template>
  <div class="rounded-xl border border-border/40 bg-surface/90 dark:bg-[#1c1c1e]/90 p-3.5 shadow-sm backdrop-blur-md">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
        </svg>
        <span class="font-semibold text-foreground text-xs">
          {{ t("research_desk.numbers_lint_title") }}
        </span>
      </div>

      <div class="flex items-center gap-2">
        <span v-if="!hasMemo" class="text-xs text-muted-foreground">
          {{ t("research_desk.no_memo_yet") }}
        </span>
        <span
          v-else
          class="font-mono text-xs font-medium"
          :class="unsupported === 0 ? 'text-emerald-500' : 'text-amber-500'"
        >
          {{ t("research_desk.numbers_supported", { supported, checked }) }}
        </span>

        <button
          v-if="hasMemo && unsupported > 0"
          type="button"
          class="rounded px-2 py-0.5 text-[11px] font-medium border border-border/40 bg-muted/30 hover:bg-muted/50 text-foreground transition-colors"
          @click="expanded = !expanded"
        >
          {{ expanded ? t("research_desk.signal_hide_formula") : `Show ${unsupported}` }}
        </button>

        <button
          type="button"
          class="rounded p-1 text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-colors"
          :title="t('research_desk.refresh')"
          :disabled="loading"
          @click="loadLint"
        >
          <svg
            class="h-3.5 w-3.5"
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

    <!-- Findings expansion -->
    <div v-if="expanded && findings.length" class="mt-3 space-y-1.5">
      <div
        v-for="(f, idx) in findings"
        :key="idx"
        class="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2 text-xs space-y-0.5"
      >
        <div class="flex items-center gap-2">
          <span class="font-mono font-bold text-amber-600 dark:text-amber-400">{{ f.number }}</span>
          <span v-if="f.section" class="text-[11px] text-muted-foreground font-medium">§ {{ f.section }}</span>
        </div>
        <p class="text-[11px] text-muted-foreground line-clamp-2">{{ f.excerpt }}</p>
      </div>
    </div>
  </div>
</template>
