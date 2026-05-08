<script setup>
import { computed } from "vue";
import {
  Building2,
  ExternalLink,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-vue-next";

const props = defineProps({
  company: { type: Object, required: true },
});

const logoUrl = computed(() =>
  props.company.logo_domain
    ? `https://logo.clearbit.com/${props.company.logo_domain}`
    : null,
);

const websiteHref = computed(() => {
  const w = props.company.website;
  if (!w) return null;
  return /^https?:\/\//i.test(w) ? w : `https://${w}`;
});

const metaItems = computed(() => {
  const c = props.company;
  const out = [];
  if (c.status) out.push(c.status);
  if (c.industry) out.push(c.industry);
  if (c.founded_year) out.push(`Founded ${c.founded_year}`);
  if (c.hq) out.push(c.hq);
  if (c.employee_band) out.push(`${c.employee_band} employees`);
  if (c.parent_company) out.push(`Parent: ${c.parent_company}`);
  return out;
});

const fundingLine = computed(() => {
  const f = props.company.latest_funding;
  if (!f) return null;
  const parts = [];
  if (f.round) parts.push(f.round);
  if (f.amount_usd) parts.push(f.amount_usd);
  if (f.lead_investor) parts.push(`led by ${f.lead_investor}`);
  if (f.post_money_usd) parts.push(`post-money ${f.post_money_usd}`);
  if (f.date) parts.push(`(${f.date})`);
  return parts.join(" · ") || null;
});

const earningsLine = computed(() => {
  const e = props.company.latest_earnings;
  if (!e) return null;
  const parts = [];
  if (e.period) parts.push(e.period);
  if (e.revenue_yoy) parts.push(`rev ${e.revenue_yoy} YoY`);
  if (e.eps) parts.push(`EPS ${e.eps}`);
  if (e.beat_or_miss) parts.push(e.beat_or_miss);
  return parts.join(" · ") || null;
});
</script>

<template>
  <header class="flex items-start gap-5 border-b border-subtle pb-6">
    <div
      class="h-14 w-14 rounded-card bg-surface-muted border border-subtle grid place-items-center shrink-0 overflow-hidden"
    >
      <img
        v-if="logoUrl"
        :src="logoUrl"
        :alt="company.name"
        class="h-full w-full object-contain"
        @error="(e) => (e.target.style.display = 'none')"
      />
      <Building2 v-else class="h-6 w-6 text-ink-muted" />
    </div>

    <div class="flex-1 min-w-0">
      <div class="text-xs uppercase tracking-wider text-ink-muted mb-1">
        Research
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <h1 class="font-display text-3xl font-semibold text-ink-primary">
          {{ company.name }}
        </h1>
        <span
          v-if="company.ticker"
          class="text-xs font-mono px-2 py-0.5 rounded bg-accent-soft text-accent-ink"
        >
          {{ company.ticker
          }}<span v-if="company.exchange" class="opacity-70">
            · {{ company.exchange }}</span
          >
        </span>
        <span v-if="company.sector" class="text-xs text-ink-muted">{{ company.sector }}</span>
        <a
          v-if="websiteHref"
          :href="websiteHref"
          target="_blank"
          rel="noopener"
          class="text-xs text-accent hover:text-accent-hover inline-flex items-center gap-1 focus-ring rounded"
        >
          <ExternalLink class="h-3 w-3" />
          <span>{{ company.website.replace(/^https?:\/\//, "") }}</span>
        </a>
      </div>

      <p
        v-if="company.description"
        class="mt-2 text-ink-secondary leading-relaxed"
      >
        {{ company.description }}
      </p>

      <div
        v-if="metaItems.length"
        class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted"
      >
        <span
          v-for="(m, i) in metaItems"
          :key="i"
        >{{ m }}<span v-if="i !== metaItems.length - 1" class="ml-3 text-ink-subtle">·</span></span>
      </div>

      <div
        v-if="company.highlight_2026 && company.highlight_2026.headline"
        class="mt-4 flex items-start gap-2 text-sm rounded-card bg-accent-soft/40 border border-accent-soft px-3 py-2"
      >
        <Sparkles class="h-3.5 w-3.5 text-accent mt-0.5 shrink-0" />
        <div class="min-w-0 flex-1">
          <span class="font-medium text-ink-primary">2026</span>
          <span class="ml-2 text-ink-primary">{{ company.highlight_2026.headline }}</span>
          <span
            v-if="company.highlight_2026.date"
            class="ml-1 text-ink-muted text-xs"
          >
            ({{ company.highlight_2026.date }})
          </span>
        </div>
      </div>

      <div v-if="fundingLine" class="mt-2 flex items-center gap-1.5 text-sm text-ink-muted">
        <TrendingUp class="h-3.5 w-3.5" />
        <span>Last round:
          <span class="text-ink-secondary">{{ fundingLine }}</span></span>
      </div>
      <div v-if="earningsLine" class="mt-1 flex items-center gap-1.5 text-sm text-ink-muted">
        <TrendingUp class="h-3.5 w-3.5" />
        <span>Last earnings:
          <span class="text-ink-secondary">{{ earningsLine }}</span></span>
      </div>

      <div
        v-if="company.key_people && company.key_people.length"
        class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-muted"
      >
        <Users class="h-3.5 w-3.5" />
        <template v-for="(p, i) in company.key_people" :key="i">
          <span>
            <span class="text-ink-secondary">{{ p.name }}</span>
            <span class="text-ink-muted"> ({{ p.role }})</span>
          </span>
          <span v-if="i !== company.key_people.length - 1" class="text-ink-subtle">·</span>
        </template>
      </div>
    </div>
  </header>
</template>
