<script setup>
import { computed, ref, watch } from "vue";
import {
  Building2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileSignature,
  Handshake,
  Languages,
  Loader2,
  Newspaper,
  Package,
  RefreshCw,
  Sparkles,
  Swords,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-vue-next";
import { api } from "../api.js";
import { appLanguage } from "../state.js";
import { useT } from "../i18n.js";

const t = useT();

const props = defineProps({
  company: { type: Object, required: true },
});
const emit = defineEmits(["refreshed"]);

// Per-page language tab. Initialized to the global app language and
// re-synced whenever the global pref changes — but the user can flip it on
// this page without affecting the rest of the app.
const viewLang = ref(appLanguage.value);
watch(appLanguage, (lang) => {
  viewLang.value = lang;
});

const translationAvailable = computed(
  () => Boolean(props.company.translation),
);

// Returns the value to display for a top-level field, picking from the
// translation block when viewLang differs from the source language and a
// translated value exists. Falls back to the source value.
function tr(field) {
  const c = props.company;
  if (viewLang.value !== "zh" && viewLang.value !== "en") return c[field];
  if (
    viewLang.value !== c.language &&
    c.translation &&
    c.translation[field] != null &&
    c.translation[field] !== ""
  ) {
    return c.translation[field];
  }
  return c[field];
}

// For nested objects/arrays — picks the translated array or object when
// available, else the source.
function trArray(field) {
  const c = props.company;
  if (
    viewLang.value !== c.language &&
    c.translation &&
    Array.isArray(c.translation[field]) &&
    c.translation[field].length === (c[field] || []).length
  ) {
    return c.translation[field];
  }
  return c[field] || [];
}

function trObject(field) {
  const c = props.company;
  if (
    viewLang.value !== c.language &&
    c.translation &&
    c.translation[field]
  ) {
    return c.translation[field];
  }
  return c[field];
}

const refreshing = ref(false);
const refreshError = ref(null);

const expanded = ref({
  products: false,
  competitors: false,
  contracts: false,
  acquisitions: false,
  news: false,
});

function toggle(key) {
  expanded.value[key] = !expanded.value[key];
}

function expandAll() {
  for (const k of Object.keys(expanded.value)) expanded.value[k] = true;
}
function collapseAll() {
  for (const k of Object.keys(expanded.value)) expanded.value[k] = false;
}

const allExpanded = computed(() =>
  Object.values(expanded.value).every(Boolean),
);

async function refresh() {
  refreshing.value = true;
  refreshError.value = null;
  try {
    const updated = await api.refreshCompany(props.company.id);
    emit("refreshed", updated);
  } catch (e) {
    refreshError.value = e.message;
  } finally {
    refreshing.value = false;
  }
}

const logoUrl = computed(() => {
  const d = props.company.logo_domain || extractDomain(props.company.website);
  return d ? `https://www.google.com/s2/favicons?domain=${d}&sz=128` : null;
});

function extractDomain(url) {
  if (!url) return null;
  try {
    const u = new URL(/^https?:\/\//i.test(url) ? url : `https://${url}`);
    return u.hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

const websiteHref = computed(() => {
  const w = props.company.website;
  if (!w) return null;
  return /^https?:\/\//i.test(w) ? w : `https://${w}`;
});

const metaItems = computed(() => {
  const c = props.company;
  const _viewLang = viewLang.value; // track for reactivity
  void _viewLang;
  const out = [];
  const status = tr("status");
  const industry = tr("industry");
  const hq = tr("hq");
  const employeeBand = tr("employee_band");
  const parent = tr("parent_company");
  if (status) out.push(status);
  if (industry) out.push(industry);
  if (c.founded_year) out.push(`Founded ${c.founded_year}`);
  if (hq) out.push(hq);
  if (employeeBand) out.push(`${employeeBand} employees`);
  if (parent) out.push(`Parent: ${parent}`);
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

const hasInsights = computed(() => {
  const c = props.company;
  return Boolean(
    (c.products && c.products.length) ||
      (c.competitors && c.competitors.length) ||
      (c.recent_news && c.recent_news.length) ||
      (c.notable_contracts && c.notable_contracts.length) ||
      (c.notable_acquisitions && c.notable_acquisitions.length),
  );
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
      <div class="flex items-start justify-between gap-3">
        <div class="text-xs uppercase tracking-wider text-ink-muted mb-1">
          {{ t("company.research_label") }}
        </div>
        <div class="flex items-center gap-2">
          <div
            v-if="translationAvailable"
            class="inline-flex rounded-md border border-subtle overflow-hidden text-xs"
            role="group"
            :title="t('lang.app_language')"
          >
            <button
              type="button"
              @click="viewLang = 'en'"
              :class="[
                'px-2 py-0.5 focus-ring transition-colors inline-flex items-center gap-1',
                viewLang === 'en'
                  ? 'bg-accent text-white'
                  : 'text-ink-secondary hover:bg-surface-muted',
              ]"
            >
              <Languages v-if="viewLang === 'en'" class="h-3 w-3" />
              EN
            </button>
            <button
              type="button"
              @click="viewLang = 'zh'"
              :class="[
                'px-2 py-0.5 focus-ring transition-colors border-l border-subtle inline-flex items-center gap-1',
                viewLang === 'zh'
                  ? 'bg-accent text-white'
                  : 'text-ink-secondary hover:bg-surface-muted',
              ]"
            >
              <Languages v-if="viewLang === 'zh'" class="h-3 w-3" />
              中
            </button>
          </div>
          <span
            v-else
            class="text-[10px] text-ink-subtle italic"
            :title="t('company.translation_unavailable')"
          >
            {{ t("company.translation_pending") }}
          </span>
          <button
            type="button"
            @click="refresh"
            :disabled="refreshing"
            class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface-muted text-ink-secondary focus-ring inline-flex items-center gap-1.5 disabled:opacity-60"
            :title="`Re-run AI search for ${company.name}`"
          >
            <Loader2 v-if="refreshing" class="h-3 w-3 animate-spin" />
            <RefreshCw v-else class="h-3 w-3" />
            <span>{{ refreshing ? t("company.refreshing") : t("company.refresh") }}</span>
          </button>
        </div>
      </div>
      <div v-if="refreshError" class="text-xs text-danger mb-1">
        {{ refreshError }}
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
        <span v-if="tr('sector')" class="text-xs text-ink-muted">{{ tr('sector') }}</span>
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
        v-if="tr('description')"
        class="mt-2 text-ink-secondary leading-relaxed"
      >
        {{ tr('description') }}
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
        v-if="trObject('highlight_2026') && trObject('highlight_2026').headline"
        class="mt-4 flex items-start gap-2 text-sm rounded-card bg-accent-soft/40 border border-accent-soft px-3 py-2"
      >
        <Sparkles class="h-3.5 w-3.5 text-accent mt-0.5 shrink-0" />
        <div class="min-w-0 flex-1">
          <span class="font-medium text-ink-primary">2026</span>
          <span class="ml-2 text-ink-primary">{{ trObject('highlight_2026').headline }}</span>
          <span
            v-if="company.highlight_2026 && company.highlight_2026.date"
            class="ml-1 text-ink-muted text-xs"
          >
            ({{ company.highlight_2026.date }})
          </span>
        </div>
      </div>

      <div v-if="fundingLine" class="mt-2 flex items-center gap-1.5 text-sm text-ink-muted">
        <TrendingUp class="h-3.5 w-3.5" />
        <span>{{ t("company.last_round") }}
          <span class="text-ink-secondary">{{ fundingLine }}</span></span>
      </div>
      <div
        v-if="company.total_funding_usd"
        class="mt-1 flex items-center gap-1.5 text-sm text-ink-muted"
      >
        <Wallet class="h-3.5 w-3.5" />
        <span>{{ t("company.total_raised") }}
          <span class="text-ink-secondary">{{ company.total_funding_usd }}</span></span>
      </div>
      <div v-if="earningsLine" class="mt-1 flex items-center gap-1.5 text-sm text-ink-muted">
        <TrendingUp class="h-3.5 w-3.5" />
        <span>{{ t("company.last_earnings") }}
          <span class="text-ink-secondary">{{ earningsLine }}</span></span>
      </div>

      <div
        v-if="trArray('key_people').length"
        class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-muted"
      >
        <Users class="h-3.5 w-3.5" />
        <template v-for="(p, i) in trArray('key_people')" :key="i">
          <span>
            <span class="text-ink-secondary">{{ p.name }}</span>
            <span class="text-ink-muted"> ({{ p.role }})</span>
          </span>
          <span v-if="i !== trArray('key_people').length - 1" class="text-ink-subtle">·</span>
        </template>
      </div>
    </div>
  </header>

  <div v-if="hasInsights" class="mt-4 space-y-2">
    <div class="flex items-center justify-between">
      <h2 class="text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {{ t("company.insights") }}
      </h2>
      <button
        type="button"
        @click="allExpanded ? collapseAll() : expandAll()"
        class="text-xs text-ink-secondary hover:text-ink-primary focus-ring rounded px-1"
      >
        {{ allExpanded ? t("company.collapse_all") : t("company.expand_all") }}
      </button>
    </div>

    <section
      v-if="trArray('products').length"
      class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
    >
      <button
        type="button"
        @click="toggle('products')"
        class="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-muted focus-ring text-left"
      >
        <span class="flex items-center gap-2 text-sm font-medium text-ink-primary">
          <Package class="h-3.5 w-3.5 text-ink-muted" />
          {{ t("company.products") }}
          <span class="text-xs text-ink-muted font-normal">
            · {{ trArray('products').length }}
          </span>
        </span>
        <ChevronDown v-if="expanded.products" class="h-4 w-4 text-ink-muted" />
        <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
      </button>
      <ul v-if="expanded.products" class="px-4 pb-3 space-y-1.5 border-t border-subtle pt-3">
        <li v-for="(p, i) in trArray('products')" :key="i" class="text-sm">
          <span class="font-medium text-ink-primary">{{ p.name }}</span>
          <span v-if="p.description" class="text-ink-secondary"> — {{ p.description }}</span>
        </li>
      </ul>
    </section>

    <section
      v-if="trArray('competitors').length"
      class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
    >
      <button
        type="button"
        @click="toggle('competitors')"
        class="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-muted focus-ring text-left"
      >
        <span class="flex items-center gap-2 text-sm font-medium text-ink-primary">
          <Swords class="h-3.5 w-3.5 text-ink-muted" />
          {{ t("company.competitors") }}
          <span class="text-xs text-ink-muted font-normal">
            · {{ trArray('competitors').length }}
          </span>
        </span>
        <ChevronDown v-if="expanded.competitors" class="h-4 w-4 text-ink-muted" />
        <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
      </button>
      <div
        v-if="expanded.competitors"
        class="px-4 pb-3 pt-3 border-t border-subtle flex flex-wrap gap-1.5"
      >
        <span
          v-for="(c, i) in trArray('competitors')"
          :key="i"
          class="text-xs px-2 py-0.5 rounded-md border border-subtle bg-surface-muted text-ink-secondary"
        >{{ c }}</span>
      </div>
    </section>

    <section
      v-if="trArray('notable_contracts').length"
      class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
    >
      <button
        type="button"
        @click="toggle('contracts')"
        class="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-muted focus-ring text-left"
      >
        <span class="flex items-center gap-2 text-sm font-medium text-ink-primary">
          <FileSignature class="h-3.5 w-3.5 text-ink-muted" />
          {{ t("company.contracts") }}
          <span class="text-xs text-ink-muted font-normal">
            · {{ trArray('notable_contracts').length }}
          </span>
        </span>
        <ChevronDown v-if="expanded.contracts" class="h-4 w-4 text-ink-muted" />
        <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
      </button>
      <ul
        v-if="expanded.contracts"
        class="px-4 pb-3 pt-3 border-t border-subtle space-y-1.5"
      >
        <li
          v-for="(k, i) in trArray('notable_contracts')"
          :key="i"
          class="text-sm flex flex-wrap items-baseline gap-x-2"
        >
          <span class="font-medium text-ink-primary">{{ k.customer }}</span>
          <span v-if="k.scope" class="text-ink-secondary">— {{ k.scope }}</span>
          <span
            v-if="company.notable_contracts && company.notable_contracts[i] && company.notable_contracts[i].value_usd"
            class="text-ink-muted text-xs"
          >{{ company.notable_contracts[i].value_usd }}</span>
          <span
            v-if="company.notable_contracts && company.notable_contracts[i] && company.notable_contracts[i].date"
            class="text-ink-muted text-xs"
          >({{ company.notable_contracts[i].date }})</span>
        </li>
      </ul>
    </section>

    <section
      v-if="trArray('notable_acquisitions').length"
      class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
    >
      <button
        type="button"
        @click="toggle('acquisitions')"
        class="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-muted focus-ring text-left"
      >
        <span class="flex items-center gap-2 text-sm font-medium text-ink-primary">
          <Handshake class="h-3.5 w-3.5 text-ink-muted" />
          {{ t("company.acquisitions") }}
          <span class="text-xs text-ink-muted font-normal">
            · {{ trArray('notable_acquisitions').length }}
          </span>
        </span>
        <ChevronDown v-if="expanded.acquisitions" class="h-4 w-4 text-ink-muted" />
        <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
      </button>
      <ul
        v-if="expanded.acquisitions"
        class="px-4 pb-3 pt-3 border-t border-subtle space-y-1.5"
      >
        <li
          v-for="(a, i) in trArray('notable_acquisitions')"
          :key="i"
          class="text-sm flex flex-wrap items-baseline gap-x-2"
        >
          <span class="font-medium text-ink-primary">{{ a.company }}</span>
          <span
            v-if="company.notable_acquisitions && company.notable_acquisitions[i] && company.notable_acquisitions[i].amount_usd"
            class="text-ink-muted text-xs"
          >{{ company.notable_acquisitions[i].amount_usd }}</span>
          <span
            v-if="company.notable_acquisitions && company.notable_acquisitions[i] && company.notable_acquisitions[i].date"
            class="text-ink-muted text-xs"
          >({{ company.notable_acquisitions[i].date }})</span>
        </li>
      </ul>
    </section>

    <section
      v-if="trArray('recent_news').length"
      class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
    >
      <button
        type="button"
        @click="toggle('news')"
        class="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-muted focus-ring text-left"
      >
        <span class="flex items-center gap-2 text-sm font-medium text-ink-primary">
          <Newspaper class="h-3.5 w-3.5 text-ink-muted" />
          {{ t("company.recent_news") }}
          <span class="text-xs text-ink-muted font-normal">
            · {{ trArray('recent_news').length }}
          </span>
        </span>
        <ChevronDown v-if="expanded.news" class="h-4 w-4 text-ink-muted" />
        <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
      </button>
      <ul
        v-if="expanded.news"
        class="px-4 pb-3 pt-3 border-t border-subtle space-y-2"
      >
        <li v-for="(n, i) in trArray('recent_news')" :key="i" class="text-sm">
          <div class="flex items-baseline gap-2">
            <span class="font-medium text-ink-primary">{{ n.headline }}</span>
            <span
              v-if="company.recent_news && company.recent_news[i] && company.recent_news[i].date"
              class="text-ink-muted text-xs"
            >{{ company.recent_news[i].date }}</span>
          </div>
          <div v-if="n.summary" class="text-ink-secondary text-xs mt-0.5">
            {{ n.summary }}
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>
