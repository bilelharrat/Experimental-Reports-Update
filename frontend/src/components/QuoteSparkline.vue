<script setup>
import { computed } from "vue";
import { sparklinePath } from "../quoteChart.js";

const props = defineProps({
  values: { type: Array, default: () => [] },
  width: { type: Number, default: 72 },
  height: { type: Number, default: 22 },
  label: { type: String, default: "" },
});

const path = computed(() =>
  sparklinePath(props.values, { width: props.width, height: props.height }),
);
const up = computed(() => {
  const nums = (props.values || []).map(Number).filter(Number.isFinite);
  if (nums.length < 2) return true;
  return nums[nums.length - 1] >= nums[0];
});
const stroke = computed(() =>
  up.value ? "rgb(var(--color-success))" : "rgb(var(--color-danger))",
);
</script>

<template>
  <svg
    v-if="path"
    class="yf-spark"
    :viewBox="`0 0 ${width} ${height}`"
    role="img"
    :aria-label="label"
  >
    <path :d="path" fill="none" :stroke="stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
  <span v-else class="text-caption1 text-ink-subtle">—</span>
</template>
