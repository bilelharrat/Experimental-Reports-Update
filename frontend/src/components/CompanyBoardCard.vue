<script setup>
import { computed, inject, ref, unref } from "vue";
import { useT } from "../i18n.js";
import { companyStatusLine } from "../companyLists.js";
import { displayTicker, lastPriceLabel, signedChange } from "../liveTicker.js";
import CompanyFollowButton from "./CompanyFollowButton.vue";
import Monogram from "./Monogram.vue";

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
      class="glass-card focus-ring flex min-h-[7.5rem] w-full flex-col rounded-card p-4 text-left active:scale-[0.99]"
      @click="emit('select', company)"
    >
      <span class="flex w-full min-w-0 items-start gap-3 pr-7">
        <Monogram :company="company" :size="36" tinted />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-callout font-semibold text-ink-primary">{{
            company.name
          }}</span>
          <span class="mt-0.5 line-clamp-2 text-footnote leading-snug text-ink-muted">
            {{ status || t("companies.status_pending") }}
          </span>
        </span>
      </span>
      <span
        v-if="ticker || lastPrice || dayMove != null"
        class="mt-auto flex w-full items-center gap-2 pt-3"
      >
        <span v-if="ticker" class="text-caption1 font-semibold tracking-wide text-ink-secondary">{{
          ticker
        }}</span>
        <span class="flex-1" />
        <span v-if="lastPrice" class="mono-data text-callout font-medium text-ink-primary">{{
          lastPrice
        }}</span>
        <span
          v-if="dayMove != null"
          class="price-pill"
          :data-up="priceUp ? 'true' : 'false'"
        >
          {{ signedChange(dayMove) }}
        </span>
      </span>
    </button>
    <div class="absolute right-2 top-2">
      <CompanyFollowButton :company-id="company.id" size="md" hide-until-hover />
    </div>
  </div>
</template>
