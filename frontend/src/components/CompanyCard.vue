<script setup>
import { computed, ref } from "vue";
import {
  ArrowRight,
  Building2,
  Loader2,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-vue-next";
import { api } from "../api.js";
import { formatCompactNumber, formatIsoDate, isPendingValue } from "../formatters.js";
import { useT } from "../i18n.js";

const props = defineProps({
  company: { type: Object, required: true },
});
const emit = defineEmits(["select", "refreshed"]);
const t = useT();

const refreshing = ref(false);

async function refresh(e) {
  e.stopPropagation();
  if (!props.company.id) return;
  refreshing.value = true;
  try {
    const updated = await api.refreshCompany(props.company.id);
    emit("refreshed", updated);
  } finally {
    refreshing.value = false;
  }
}

const metaLine = computed(() => {
  const parts = [];
  if (props.company.founded_year) parts.push(`${t("company.founded")} ${props.company.founded_year}`);
  if (props.company.hq) parts.push(props.company.hq);
  if (props.company.employee_band) parts.push(`${props.company.employee_band} ${t("company.employees")}`);
  if (props.company.status) parts.push(props.company.status);
  return parts.join(" · ");
});

const fundingLine = computed(() => {
  const f = props.company.latest_funding;
  if (!f) return null;
  const parts = [];
  if (f.round) parts.push(f.round);
  if (!isPendingValue(f.amount_usd)) parts.push(formatCompactNumber(f.amount_usd, { currency: true }));
  if (!isPendingValue(f.post_money_usd)) parts.push(`${t("company.post_money")} ${formatCompactNumber(f.post_money_usd, { currency: true })}`);
  if (f.lead_investor) parts.push(t("company.led_by", { investor: f.lead_investor }));
  if (f.date) parts.push(`(${formatIsoDate(f.date)})`);
  return parts.join(" · ") || null;
});

const earningsLine = computed(() => {
  const e = props.company.latest_earnings;
  if (!e) return null;
  const parts = [];
  if (e.period) parts.push(e.period);
  if (e.revenue_yoy) parts.push(t("company.revenue_yoy", { value: e.revenue_yoy }));
  if (e.eps) parts.push(`EPS ${e.eps}`);
  if (e.beat_or_miss) parts.push(e.beat_or_miss);
  return parts.join(" · ") || null;
});
</script>

<template>
  <button
    type="button"
    @click="emit('select', company)"
    class="w-full text-left p-5 rounded-card bg-surface hover:bg-fill-tertiary shadow-card focus-ring transition flex items-start gap-4"
  >
    <div
      class="h-11 w-11 rounded-subbox bg-fill-tertiary grid place-items-center shrink-0 overflow-hidden"
    >
      <Building2 class="h-5 w-5 text-ink-muted" />
    </div>

    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 flex-wrap">
        <div class="font-display font-semibold text-ink-primary text-base">
          {{ company.name }}
        </div>
        <span
          v-if="company.ticker"
          class="text-xs font-mono px-1.5 py-0.5 rounded bg-accent-soft text-accent-ink"
        >
          {{ company.ticker }}<span v-if="company.exchange" class="opacity-70"> · {{ company.exchange }}</span>
        </span>
        <span v-if="company.category" class="text-xs text-ink-muted">{{ company.category }}</span>
      </div>

      <p
        v-if="company.description"
        class="mt-1.5 text-sm text-ink-secondary leading-relaxed"
      >
        {{ company.description }}
      </p>

      <div v-if="metaLine" class="mt-2 text-xs text-ink-muted">{{ metaLine }}</div>

      <div
        v-if="company.highlight_2026"
        class="mt-3 flex items-start gap-2 text-sm rounded-lg bg-accent-soft/40 border border-accent-soft px-3 py-2"
      >
        <Sparkles class="h-3.5 w-3.5 text-accent mt-0.5 shrink-0" />
        <div class="min-w-0 flex-1">
          <span class="text-ink-primary">{{ company.highlight_2026.headline }}</span>
          <span v-if="company.highlight_2026.date" class="ml-1 text-ink-muted text-xs">
            ({{ company.highlight_2026.date }})
          </span>
        </div>
      </div>

      <div v-if="fundingLine" class="mt-2 flex items-center gap-1.5 text-xs text-ink-muted">
        <TrendingUp class="h-3 w-3" />
        <span>{{ t("company.last_round") }} <span class="mono-data text-ink-secondary">{{ fundingLine }}</span></span>
      </div>
      <div v-if="earningsLine" class="mt-1 flex items-center gap-1.5 text-xs text-ink-muted">
        <TrendingUp class="h-3 w-3" />
        <span>{{ t("company.last_earnings") }} <span class="text-ink-secondary">{{ earningsLine }}</span></span>
      </div>

      <div
        v-if="company.key_people && company.key_people.length"
        class="mt-2 flex items-center gap-1.5 text-xs text-ink-muted"
      >
        <Users class="h-3 w-3" />
        <span class="truncate">
          <template v-for="(p, i) in company.key_people.slice(0, 3)" :key="i">
            <span v-if="i > 0"> · </span>
            <span class="text-ink-secondary">{{ p.name }}</span>
            <span> ({{ p.role }})</span>
          </template>
        </span>
      </div>
    </div>

    <div class="flex flex-col items-end gap-1.5 shrink-0">
      <span
        v-if="company.id"
        @click="refresh"
        :title="`Re-run AI search for ${company.name}`"
        class="text-ink-muted hover:text-accent p-1 rounded focus-ring cursor-pointer"
      >
        <Loader2 v-if="refreshing" class="h-3.5 w-3.5 animate-spin" />
        <RefreshCw v-else class="h-3.5 w-3.5" />
      </span>
      <ArrowRight class="h-4 w-4 text-ink-muted" />
    </div>
  </button>
</template>
