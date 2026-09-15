<script setup>
import { RouterLink } from "vue-router";
import { quoteStaleness, signedChange } from "../liveTicker.js";
import { useT } from "../i18n.js";

const props = defineProps({
  items: { type: Array, default: () => [] },
  linkToTracking: { type: Boolean, default: false },
  label: { type: String, default: "" },
});

const emit = defineEmits(["select"]);
const t = useT();

function title() {
  return props.label || t("tracking.live_tape");
}

function asOfHint(item) {
  const stale = quoteStaleness(item?.quote?.as_of || item?.asOf);
  if (!stale) return "";
  if (stale.stale) return t("radar.stale_quote", { n: stale.ageMinutes });
  if (stale.ageMinutes < 1) return t("home.cache_just_now");
  if (stale.ageMinutes < 60) return t("home.cache_minutes_ago", { n: stale.ageMinutes });
  return "";
}
</script>

<template>
  <section
    v-if="items.length"
    class="ticker-tape"
    :aria-label="title()"
  >
    <div class="flex shrink-0 items-center gap-1.5 pl-1 pr-3 text-caption1 font-semibold text-ink-muted">
      <span class="live-pulse status-dot bg-success"></span>
      <RouterLink
        v-if="linkToTracking"
        :to="{ name: 'tracking' }"
        class="rounded-[6px] hover:text-ink-primary focus-ring"
      >
        {{ title() }}
      </RouterLink>
      <span v-else>{{ title() }}</span>
    </div>
    <div class="ticker-tape-track">
      <button
        v-for="item in items"
        :key="item.ticker"
        type="button"
        class="ticker-tape-item focus-ring"
        @click="emit('select', { id: item.companyId, ticker: item.ticker, name: item.name })"
      >
        <span class="text-footnote font-semibold text-ink-primary">{{ item.ticker }}</span>
        <span v-if="item.lastPrice" class="mono-data text-footnote text-ink-secondary">
          {{ item.lastPrice }}
        </span>
        <span
          v-if="item.day != null"
          class="mono-data text-footnote font-semibold"
          :class="item.up ? 'text-success' : 'text-danger'"
        >
          {{ signedChange(item.day) }}
        </span>
        <span v-else class="text-caption1 text-ink-subtle">
          {{ t("tracking.quote_pending") }}
        </span>
        <span
          v-if="asOfHint(item)"
          class="text-caption2"
          :class="quoteStaleness(item?.quote?.as_of || item?.asOf)?.stale ? 'text-warning-ink' : 'text-ink-subtle'"
        >
          {{ asOfHint(item) }}
        </span>
      </button>
    </div>
  </section>
</template>
