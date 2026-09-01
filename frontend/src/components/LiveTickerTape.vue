<script setup>
import { RouterLink } from "vue-router";
import { signedChange } from "../liveTicker.js";
import { useT } from "../i18n.js";

defineProps({
  items: { type: Array, default: () => [] },
  linkToTracking: { type: Boolean, default: false },
});

const emit = defineEmits(["select"]);
const t = useT();
</script>

<template>
  <section
    v-if="items.length"
    class="overflow-x-auto rounded-card bg-surface px-4 py-3 shadow-card"
    :aria-label="t('tracking.live_tape')"
  >
    <div class="mb-2 flex items-center gap-2 text-caption1 text-ink-muted">
      <span class="live-pulse h-1.5 w-1.5 rounded-full bg-accent"></span>
      <RouterLink
        v-if="linkToTracking"
        :to="{ name: 'tracking' }"
        class="hover:text-ink-primary focus-ring rounded-subbox"
      >
        {{ t("tracking.live_tape") }}
      </RouterLink>
      <span v-else>{{ t("tracking.live_tape") }}</span>
    </div>
    <div class="flex min-w-max items-stretch gap-4">
      <button
        v-for="item in items"
        :key="item.ticker"
        type="button"
        class="flex items-baseline gap-2 rounded-subbox text-left focus-ring"
        @click="item.companyId && emit('select', { id: item.companyId })"
      >
        <span class="mono-data font-semibold text-ink-primary">{{ item.ticker }}</span>
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
      </button>
    </div>
  </section>
</template>
