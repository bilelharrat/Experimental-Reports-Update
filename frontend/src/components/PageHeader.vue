<script setup>
// Large title at the top of a desk (MacDeskHeader). While it is on screen the
// toolbar keeps its small title hidden; scroll it away and the toolbar title
// fades in.
import { ref } from "vue";
import { useLargeTitle } from "../chrome.js";

defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
});

const titleEl = ref(null);
useLargeTitle(titleEl);
</script>

<template>
  <header class="page-header">
    <div class="min-w-0">
      <slot name="eyebrow" />
      <h1 ref="titleEl" class="page-title">
        <slot name="title">{{ title }}</slot>
      </h1>
      <p v-if="subtitle || $slots.subtitle" class="page-subtitle">
        <slot name="subtitle">{{ subtitle }}</slot>
      </p>
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </header>
</template>
