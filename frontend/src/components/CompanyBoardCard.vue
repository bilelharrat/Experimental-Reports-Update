<script setup>
import { computed } from "vue";
import { useT } from "../i18n.js";
import { companyStatusLine } from "../companyLists.js";
import CompanyFollowButton from "./CompanyFollowButton.vue";

const props = defineProps({
  company: { type: Object, required: true },
});
const emit = defineEmits(["select"]);
const t = useT();

const status = computed(() => companyStatusLine(props.company, t));
</script>

<template>
  <div class="group relative">
    <button
      type="button"
      class="glass-card focus-ring flex min-h-[7.5rem] w-full flex-col items-start rounded-glass p-4 text-left transition hover:-translate-y-0.5"
      @click="emit('select', company)"
    >
      <span class="text-callout font-semibold text-ink-primary">{{ company.name }}</span>
      <span class="mt-1 line-clamp-3 text-footnote leading-snug text-ink-muted">
        {{ status || t("companies.status_pending") }}
      </span>
    </button>
    <div class="absolute right-2 top-2">
      <CompanyFollowButton :company-id="company.id" size="md" hide-until-hover />
    </div>
  </div>
</template>
