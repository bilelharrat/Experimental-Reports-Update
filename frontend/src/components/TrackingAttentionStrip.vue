<script setup>
import { RouterLink } from "vue-router";
import { trackingActionLabel, trackingAttentionLabel } from "../trackingLabels.js";
import { useT } from "../i18n.js";

defineProps({
  items: { type: Array, default: () => [] },
});

defineEmits(["inspect"]);

const t = useT();
</script>

<template>
  <section v-if="items.length" class="space-y-2">
    <article
      v-for="item in items"
      :key="item.id"
      class="flex items-center gap-2 rounded-card bg-surface px-4 py-3 shadow-card"
    >
      <RouterLink
        :to="item.route"
        class="flex min-w-0 flex-1 items-center gap-3 hover:bg-fill-tertiary/70 focus-ring rounded-subbox"
      >
        <span
          class="h-2 w-2 shrink-0 rounded-pill"
          :class="item.severity === 'high' ? 'bg-danger' : 'bg-warning'"
        ></span>
        <span class="min-w-0 flex-1">
          <span class="font-medium text-ink-primary">{{ item.company_name }}</span>
          <span class="text-ink-muted"> · {{ trackingAttentionLabel(item, t) }}</span>
        </span>
        <span class="shrink-0 text-footnote font-medium text-accent">
          {{ trackingActionLabel(item, t) }}
        </span>
      </RouterLink>
      <button
        type="button"
        class="shrink-0 text-caption1 font-medium text-accent hover:underline focus-ring rounded-subbox px-1"
        @click="$emit('inspect', item)"
      >
        {{ t("copilot.ask") }}
      </button>
    </article>
  </section>
</template>
