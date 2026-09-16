<script setup>
// Rounded-square logo or initials, the web twin of MacMonogram.
// Tries to render the company's real logo first (zero-cost via Google Favicon CDN
// and public vector mirrors). If unavailable or offline, gracefully falls back
// to squircle initials (neutral glass by default; tinted picks one of ten system
// colors from a stable hash of the company id).
import { computed, ref, watch } from "vue";
import {
  accountInitials,
  companyFallbackLogoUrl,
  companyInitials,
  companyLogoUrl,
} from "../formatters.js";

const props = defineProps({
  company: { type: Object, default: null },
  name: { type: String, default: "" },
  // Explicit initials win over anything derived from company or name.
  initials: { type: String, default: "" },
  size: { type: Number, default: 28 },
  tinted: { type: Boolean, default: false },
  round: { type: Boolean, default: false },
  showLogo: { type: Boolean, default: true },
  logoUrl: { type: String, default: "" },
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

const primaryLogo = computed(() => {
  if (!props.showLogo) return "";
  if (props.logoUrl) return props.logoUrl;
  return props.company ? companyLogoUrl(props.company) : "";
});

const fallbackLogo = computed(() => {
  if (!props.showLogo) return "";
  return props.company ? companyFallbackLogoUrl(props.company) : "";
});

const currentSrc = ref("");
const imageLoaded = ref(false);
const imageFailed = ref(false);

watch(
  [primaryLogo, fallbackLogo],
  ([nextPrimary]) => {
    currentSrc.value = nextPrimary || "";
    imageLoaded.value = false;
    imageFailed.value = !nextPrimary;
  },
  { immediate: true }
);

function onImageLoad() {
  imageLoaded.value = true;
  imageFailed.value = false;
}

function onImageError() {
  if (
    currentSrc.value === primaryLogo.value &&
    fallbackLogo.value &&
    fallbackLogo.value !== primaryLogo.value
  ) {
    currentSrc.value = fallbackLogo.value;
  } else {
    imageFailed.value = true;
    imageLoaded.value = false;
  }
}

const hasLogo = computed(() => props.showLogo && imageLoaded.value && !imageFailed.value);
const hasCandidate = computed(() => props.showLogo && Boolean(currentSrc.value) && !imageFailed.value);
</script>

<template>
  <span
    class="monogram"
    :class="[
      round ? '!rounded-full' : '',
      hasLogo ? 'monogram-has-logo' : '',
    ]"
    :data-tint="hasLogo ? undefined : tint"
    :style="{ '--mono-size': `${size}px` }"
    aria-hidden="true"
  >
    <img
      v-if="hasCandidate"
      v-show="imageLoaded"
      :src="currentSrc"
      :alt="props.company?.name || props.name || ''"
      loading="eager"
      decoding="async"
      referrerpolicy="no-referrer"
      class="monogram-logo"
      @load="onImageLoad"
      @error="onImageError"
    />
    <span v-if="!imageLoaded" class="monogram-initials">{{ initials }}</span>
  </span>
</template>
