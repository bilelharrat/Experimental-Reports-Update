<script setup>
import { computed } from "vue";
import Monogram from "../Monogram.vue";

const props = defineProps({
  name: {
    type: String,
    required: true,
  },
  ticker: {
    type: String,
    default: "",
  },
  size: {
    type: Number,
    default: 30,
  },
  indicator: {
    type: Boolean,
    default: false,
  },
  company: {
    type: Object,
    default: null,
  },
  showLogo: {
    type: Boolean,
    default: true,
  },
  logoUrl: {
    type: String,
    default: "",
  },
});

const resolvedCompany = computed(() => {
  if (props.company && typeof props.company === "object") {
    return {
      ...props.company,
      name: props.company.name || props.name,
      ticker: props.company.ticker || props.ticker,
    };
  }
  return {
    id: props.ticker || props.name,
    name: props.name,
    ticker: props.ticker,
  };
});
</script>

<template>
  <div
    class="relative shrink-0 select-none inline-flex items-center justify-center"
    :style="{ width: `${size}px`, height: `${size}px` }"
  >
    <Monogram
      :company="resolvedCompany"
      :name="name"
      :size="size"
      :show-logo="showLogo"
      :logo-url="logoUrl"
      tinted
    />

    <!-- Modified pip: Circle().fill(.accentColor) stroked with Color.dsCard,
         offset (3, -3), from CompanyListRow in MacResearchDeskView.swift -->
    <div
      v-if="indicator"
      class="absolute z-10 h-2 w-2 rounded-full"
      style="
        top: -3px;
        right: -3px;
        background: var(--mac-accent, #007aff);
        box-shadow: 0 0 0 1.5px var(--mac-card, #fff);
      "
    />
  </div>
</template>
