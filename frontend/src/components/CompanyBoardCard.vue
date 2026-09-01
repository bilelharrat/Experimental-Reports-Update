<script setup>
import { computed, inject, ref, unref } from "vue";
import { useT } from "../i18n.js";
import { companyStatusLine } from "../companyLists.js";
import { displayTicker, lastPriceLabel, signedChange } from "../liveTicker.js";
import CompanyFollowButton from "./CompanyFollowButton.vue";

const props = defineProps({
  company: { type: Object, required: true },
  quote: { type: Object, default: null },
});
const emit = defineEmits(["select"]);
const t = useT();
const workspaceCompanies = inject("workspaceCompanies", ref([]));

const status = computed(() => companyStatusLine(props.company, t));
const ticker = computed(() =>
  displayTicker(props.company, unref(workspaceCompanies) || []),
);
const lastPrice = computed(() =>
  lastPriceLabel(
    props.quote?.last_price != null
      ? { last: Number(props.quote.last_price), currency: props.quote.currency || "USD" }
      : null,
  ),
);
const dayMove = computed(() => {
  const day = props.quote?.change_pct_1d;
  return day == null ? null : Number(day);
});
const priceUp = computed(() => dayMove.value != null && dayMove.value >= 0);
</script>

<template>
  <div class="group relative">
    <button
      type="button"
      class="glass-card focus-ring flex min-h-[7.5rem] w-full flex-col items-start rounded-glass p-4 text-left transition hover:-translate-y-0.5"
      @click="emit('select', company)"
    >
      <span class="flex w-full min-w-0 items-start justify-between gap-3 pr-8">
        <span class="min-w-0">
          <span class="block truncate text-callout font-semibold text-ink-primary">{{
            company.name
          }}</span>
          <span class="mt-1 line-clamp-3 text-footnote leading-snug text-ink-muted">
            {{ status || t("companies.status_pending") }}
          </span>
        </span>
        <span v-if="lastPrice || dayMove != null" class="shrink-0 text-right">
          <span v-if="ticker" class="block font-mono text-caption1 text-ink-muted">{{
            ticker
          }}</span>
          <span v-if="lastPrice" class="block mono-data text-callout text-ink-primary">{{
            lastPrice
          }}</span>
          <span
            v-if="dayMove != null"
            class="block mono-data text-caption1 font-semibold"
            :class="priceUp ? 'text-success' : 'text-danger'"
          >
            {{ signedChange(dayMove) }}
          </span>
        </span>
      </span>
    </button>
    <div class="absolute right-2 top-2">
      <CompanyFollowButton :company-id="company.id" size="md" hide-until-hover />
    </div>
  </div>
</template>
