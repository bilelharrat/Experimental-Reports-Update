<script setup>
// Warren's portrait: the Ask mark, as on iPhone (AskMark.swift). AiMark stays
// the icon for generic AI features (summaries, memo runs).
import warrenUrl from "../assets/warren.jpg";

defineProps({
  size: { type: Number, default: 28 },
  // While Warren is answering, a soft ring breathes around the portrait.
  busy: { type: Boolean, default: false },
});
</script>

<template>
  <span
    class="warren-mark"
    :data-busy="busy ? 'true' : 'false'"
    :style="{ '--warren-size': `${size}px` }"
    aria-hidden="true"
  >
    <img :src="warrenUrl" alt="" draggable="false" decoding="async" />
  </span>
</template>
