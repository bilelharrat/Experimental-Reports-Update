<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { ChevronRight, Loader2 } from "lucide-vue-next";
import { api } from "../api.js";
import { lastPriceLabel, signedChange } from "../liveTicker.js";
import { quoteMovers } from "../homeDesk.js";
import { useT } from "../i18n.js";

const props = defineProps({
  companies: { type: Array, default: () => [] },
  quotes: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["open-company"]);

const t = useT();
const loading = ref(false);
const error = ref("");
const payload = ref(null);

const summary = computed(() => payload.value?.summary || {});
const sections = computed(() => payload.value?.sections || {});
const regime = computed(() => sections.value.market_regime || {});
const signals = computed(() => (sections.value.ranked_signals || []).slice(0, 3));
const movers = computed(() => quoteMovers(props.companies, props.quotes, 6));

const posture = computed(() => String(regime.value.posture || "empty"));
const postureLabel = computed(() => {
  const key = `home.desk_posture_${posture.value.replace("-", "_")}`;
  const label = t(key);
  return label === key ? posture.value : label;
});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    payload.value = await api.researchPages.marketPulse();
  } catch (e) {
    error.value = e.message || t("home.desk_market_error");
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function openMover(row) {
  const company = props.companies.find((c) => String(c.id) === String(row.id));
  if (company) emit("open-company", company);
}

function moverPrice(row) {
  return lastPriceLabel(
    row.last != null ? { last: Number(row.last), currency: row.currency } : null,
  );
}
</script>

<template>
  <section>
    <div class="mb-2 flex items-end justify-between px-1">
      <h2 class="font-display text-title2 text-ink-primary">
        {{ t("home.desk_market_title") }}
      </h2>
      <RouterLink
        class="text-footnote font-medium text-accent-ink focus-ring rounded-pill px-1"
        :to="{ name: 'weekly-summary' }"
      >
        {{ t("home.desk_open_pulse") }}
      </RouterLink>
    </div>

    <div v-if="loading" class="news-grouped flex items-center gap-2 px-4 py-5 text-callout text-ink-muted">
      <Loader2 class="h-4 w-4 animate-spin" />
      {{ t("common.loading") }}
    </div>
    <p v-else-if="error" class="news-grouped px-4 py-4 text-callout text-danger">{{ error }}</p>

    <div v-else class="space-y-3">
      <div class="news-grouped px-4 py-3">
        <div class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
          {{ postureLabel }}
        </div>
        <p class="mt-1 text-footnote text-ink-secondary">
          {{
            t("home.desk_breadth", {
              up: regime.breadth?.positive_signals || 0,
              down: regime.breadth?.negative_signals || 0,
              flat: regime.breadth?.neutral_signals || 0,
            })
          }}
        </p>
        <p v-if="summary.top_signal" class="mt-1 text-callout text-ink-primary">
          {{ summary.top_signal }}
        </p>
      </div>

      <div class="news-grouped overflow-hidden">
        <div class="px-4 pb-1 pt-3 text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
          {{ t("home.desk_movers") }}
        </div>
        <p v-if="movers.length === 0" class="px-4 pb-4 pt-2 text-callout text-ink-muted">
          {{ t("home.desk_movers_empty") }}
        </p>
        <button
          v-for="row in movers"
          :key="row.id"
          type="button"
          class="news-story-row focus-ring"
          @click="openMover(row)"
        >
          <span class="min-w-0 flex-1">
            <span class="block font-display text-headline tabular text-ink-primary">{{ row.ticker }}</span>
            <span class="block truncate text-caption1 text-ink-muted">{{ row.name }}</span>
          </span>
          <span class="shrink-0 text-right">
            <span v-if="moverPrice(row)" class="block text-footnote tabular text-ink-primary">{{ moverPrice(row) }}</span>
            <span
              class="inline-flex rounded-md px-1.5 py-0.5 text-caption1 font-semibold tabular"
              :class="row.change >= 0 ? 'bg-success-soft text-success-ink' : 'bg-danger-soft text-danger-ink'"
            >
              {{ signedChange(row.change) }}
            </span>
          </span>
        </button>
      </div>

      <div v-if="signals.length" class="news-grouped overflow-hidden">
        <div class="px-4 pb-1 pt-3 text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
          {{ t("home.desk_signals") }}
        </div>
        <div
          v-for="signal in signals"
          :key="signal.signal_id || signal.signal"
          class="news-story-row pointer-events-none"
        >
          <div class="min-w-0">
            <div class="text-headline text-ink-primary">{{ signal.signal || signal.title }}</div>
            <div class="mt-0.5 text-caption1 text-ink-muted">
              {{ signal.ticker || signal.theme || signal.direction }}
            </div>
          </div>
        </div>
      </div>

      <RouterLink
        class="flex items-center justify-between px-1 text-footnote font-medium text-accent-ink focus-ring rounded-pill"
        :to="{ name: 'tracking' }"
      >
        {{ t("home.desk_open_tracking") }}
        <ChevronRight class="h-4 w-4" />
      </RouterLink>
    </div>
  </section>
</template>
