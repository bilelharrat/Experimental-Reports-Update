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

    <!-- Modified indicator pip matching MacResearchDeskView: line 143 -->
    <div
      v-if="indicator"
      class="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-blue-500 ring-[1.5px] ring-[#18181a] z-10"
    />
  </div>
</template>
