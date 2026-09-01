<script setup>
import { computed } from "vue";
import { Star } from "lucide-vue-next";
import { useT } from "../i18n.js";
import { toggleTrackedCompany, trackedCompanyIds } from "../state.js";

const props = defineProps({
  companyId: { type: [String, Number], required: true },
  size: { type: String, default: "sm" },
  hideUntilHover: { type: Boolean, default: false },
});

const t = useT();
const followed = computed(() =>
  trackedCompanyIds.value.has(String(props.companyId || "")),
);
const label = computed(() =>
  followed.value ? t("sidebar.unfollow") : t("sidebar.follow"),
);
</script>

<template>
  <button
    type="button"
    class="icon-btn"
    :class="[
      size === 'md' ? '!h-7 !w-7' : '!h-6 !w-6',
      hideUntilHover && !followed
        ? 'opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100'
        : '',
    ]"
    :aria-label="label"
    :title="label"
    :aria-pressed="followed"
    @click.stop.prevent="toggleTrackedCompany(companyId)"
  >
    <Star
      :class="[
        size === 'md' ? 'h-4 w-4' : 'h-3.5 w-3.5',
        followed ? 'text-notice' : '',
      ]"
      :fill="followed ? 'currentColor' : 'none'"
    />
  </button>
</template>
