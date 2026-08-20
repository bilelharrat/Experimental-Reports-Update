<script setup>
import { computed } from "vue";
import { Radar, Star } from "lucide-vue-next";
import { useT } from "../i18n.js";
import { companyStatusLine } from "../companyLists.js";
import {
  favoriteCompanyIds,
  toggleFavoriteCompany,
  toggleTrackedCompany,
  trackedCompanyIds,
} from "../state.js";

const props = defineProps({
  company: { type: Object, required: true },
});
const emit = defineEmits(["select"]);
const t = useT();

const status = computed(() => companyStatusLine(props.company, t));
const favorited = computed(() => favoriteCompanyIds.value.has(String(props.company.id)));
const tracked = computed(() => trackedCompanyIds.value.has(String(props.company.id)));
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
    <div class="absolute right-2 top-2 flex gap-0.5">
      <button
        type="button"
        class="icon-btn h-7 w-7"
        :class="favorited ? '' : 'opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100'"
        :aria-label="favorited ? t('sidebar.unfavorite') : t('sidebar.favorite')"
        :aria-pressed="favorited"
        @click.stop="toggleFavoriteCompany(company.id)"
      >
        <Star
          class="h-3.5 w-3.5"
          :class="favorited ? 'text-warning' : ''"
          :fill="favorited ? 'currentColor' : 'none'"
        />
      </button>
      <button
        type="button"
        class="icon-btn h-7 w-7"
        :class="tracked ? '' : 'opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100'"
        :aria-label="tracked ? t('sidebar.untrack_company') : t('sidebar.track_company')"
        :aria-pressed="tracked"
        @click.stop="toggleTrackedCompany(company.id)"
      >
        <Radar class="h-3.5 w-3.5" :class="tracked ? 'text-accent-ink' : ''" />
      </button>
    </div>
  </div>
</template>
