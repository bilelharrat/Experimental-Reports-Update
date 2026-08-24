<script setup>
import orbUrl from "../assets/ai-orb.png";

defineOptions({ inheritAttrs: false });
</script>

<template>
  <img
    :src="orbUrl"
    alt=""
    aria-hidden="true"
    draggable="false"
    v-bind="$attrs"
    class="inline-block object-contain select-none"
  />
</template>
