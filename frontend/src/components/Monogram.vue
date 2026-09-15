<script setup>
// Rounded-square initials, the web twin of MacMonogram. Neutral glass by
// default; `tinted` picks one of ten system colors from a stable hash of the
// company id so a company keeps its color across sessions and devices.
import { computed } from "vue";
import { accountInitials, companyInitials } from "../formatters.js";

const props = defineProps({
  company: { type: Object, default: null },
  name: { type: String, default: "" },
  // Explicit initials win over anything derived from company or name.
  initials: { type: String, default: "" },
  size: { type: Number, default: 28 },
  tinted: { type: Boolean, default: false },
  round: { type: Boolean, default: false },
});

const initials = computed(() => {
  if (props.initials) return props.initials;
  return props.company ? companyInitials(props.company) : accountInitials(props.name, "?");
});

const tint = computed(() => {
  if (!props.tinted) return undefined;
  const key = String(props.company?.id || props.company?.name || props.name || "");
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  }
  return String(hash % 10);
});
</script>

<template>
  <span
    class="monogram"
    :class="round ? '!rounded-full' : ''"
    :data-tint="tint"
    :style="{ '--mono-size': `${size}px` }"
    aria-hidden="true"
  >{{ initials }}</span>
</template>
