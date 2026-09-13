<script setup>
/**
 * Web mark matching iOS `PulseECGShape` / `PulseECGTabIcon`
 * (ios/BSHResearch/Views/Shared/PulseECGIcon.swift).
 *
 * Normalized path: baseline 0.50, raised S-valley = 0.50 + (0.94-0.50)*0.75.
 * Drawable inset mirrors the UIKit renderer (≈1.5×4.5 on a 25pt cell → 24 viewBox).
 */
defineProps({
  size: { type: [Number, String], default: 18 },
  /** Stroke in viewBox units; iOS uses ~1.85pt on a 25pt cell. */
  strokeWidth: { type: [Number, String], default: 1.85 },
});

// viewBox 0 0 24 24; inset rect ≈ (1.44, 4.32) size 21.12 × 15.36
// Raised S-valley y = 4.32 + 0.83*15.36 ≈ 17.07 (not the deep SF trough).
const ECG_PATH =
  "M1.44 12 L4.40 12 L5.66 9.85 L6.93 12 L7.78 13.23 L9.47 5.24 L11.16 17.07 L12.42 12 L14.11 8.93 L16.22 12 L22.56 12";
</script>

<template>
  <svg
    :width="size"
    :height="size"
    class="shrink-0"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="ECG_PATH" />
  </svg>
</template>
