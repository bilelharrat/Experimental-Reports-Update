<script setup>
// The Berkeley Summit House twin-peak mark, drawn in currentColor so it
// follows the theme (assets/berkeley-summit-house-mark.svg is fixed black).
defineProps({
  size: { type: [Number, String], default: 20 },
});
</script>

<template>
  <svg
    :width="size"
    :height="Math.round(Number(size) * 0.644)"
    viewBox="0 0 101 65"
    fill="currentColor"
    aria-hidden="true"
    class="shrink-0"
  >
    <path
      d="M54.2302 10.179L73.2761 44.8541C73.974 46.119 75.5732 46.5843 76.8381 45.8573L89.6323 38.5733C91.0426 37.7737 92.8309 38.4425 93.3688 39.9836L100.609 60.876C101.191 62.5625 99.9404 64.3217 98.1521 64.3217H38.9499C37.2488 64.3217 36.013 62.7224 36.4346 61.0795L49.4469 10.7751C50.0285 8.49246 53.1107 8.11445 54.2302 10.179Z"
    />
    <path
      d="M36.202 40.3179L29.0925 62.5333C28.7436 63.6091 27.755 64.3361 26.6209 64.3361H3.48961C0.974389 64.3361 -0.0724086 61.1375 1.94849 59.6546L32.1893 37.4392C34.2102 35.9562 36.9726 37.9335 36.202 40.3179Z"
    />
  </svg>
</template>
