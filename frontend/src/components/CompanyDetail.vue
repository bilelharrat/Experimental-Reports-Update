<script setup>
import { computed, ref, watch } from "vue";
import {
  Building2,
  ExternalLink,
  Loader2,
  RefreshCw,
  UserRound,
} from "lucide-vue-next";
import { api } from "../api.js";
import { appLanguage } from "../state.js";
import TraderView from "./TraderView.vue";

const props = defineProps({
  company: { type: Object, required: true },
});
const emit = defineEmits(["refreshed"]);

const viewLang = ref(appLanguage.value);
watch(appLanguage, (lang) => {
  viewLang.value = lang;
});

const refreshing = ref(false);
const refreshError = ref(null);

function wantsTranslation() {
  const c = props.company;
  if (!c.translation) return false;
  const srcZh = c.language === "zh";
  if (viewLang.value === "zh") return !srcZh;
  if (viewLang.value === "en") return srcZh;
  return false;
}

function tr(field) {
  const c = props.company;
  if (
    wantsTranslation() &&
    c.translation[field] != null &&
    c.translation[field] !== ""
  ) {
    return c.translation[field];
  }
  return c[field];
}

function trArray(field) {
  const c = props.company;
  if (
    wantsTranslation() &&
    Array.isArray(c.translation[field]) &&
    c.translation[field].length
  ) {
    return c.translation[field];
  }
  return c[field] || [];
}

function monogram(name) {
  return String(name || "?")
    .replace(/[,.]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

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

const websiteHref = computed(() => {
  const w = props.company.website;
  if (!w) return null;
  return /^https?:\/\//i.test(w) ? w : `https://${w}`;
});

const positioningText = computed(() => {
  const p = props.company.positioning || {};
  if (p.category || p.customers || p.need || p.benefit) {
    return `${props.company.name} is a ${p.category || "company"} for ${
      p.customers || "customers"
    } who ${p.need || "have a defined need"}, that ${
      p.benefit || "delivers a measurable benefit"
    }. Unlike ${p.alternative || "the incumbent alternative"}, it ${
      p.differentiator || "has a differentiated approach"
    }.`;
  }
  return tr("description") || "Positioning summary is pending source enrichment.";
});

const metrics = computed(() => {
  const rows = Array.isArray(props.company.metrics) ? props.company.metrics : [];
  if (rows.length) return rows;
  return [
    { label: "ARR", value: "Unknown", source_class: "source pending" },
    { label: "YoY Growth", value: "Unknown", source_class: "source pending" },
    {
      label: "Valuation",
      value: props.company.latest_funding?.post_money_usd || "Unknown",
      source_class: props.company.latest_funding ? "company record" : "source pending",
      as_of: props.company.latest_funding?.date,
    },
    { label: "TAM", value: "Unknown", source_class: "source pending" },
  ];
});

const team = computed(() => {
  const typed = props.company.team_profiles || props.company.team || [];
  const rows = Array.isArray(typed) && typed.length ? typed : trArray("key_people");
  return rows.map((person) =>
    typeof person === "string" ? { name: person, role: "" } : person,
  );
});

const products = computed(() =>
  trArray("products").map((product, index) =>
    typeof product === "string"
      ? { id: `product-${index}`, name: product, description: "" }
      : { id: product.id || `product-${index}`, ...product },
  ),
);

const competitors = computed(() =>
  (
    Array.isArray(props.company.competitor_cards) &&
    props.company.competitor_cards.length
      ? props.company.competitor_cards
      : trArray("competitors")
  ).map((competitor, index) =>
    typeof competitor === "string"
      ? {
          id: competitor.toLowerCase().replace(/[^\w]+/g, "-"),
          name: competitor,
          status: "Private",
          note: "Comparison profile pending.",
        }
      : {
          id: competitor.id || competitor.name?.toLowerCase().replace(/[^\w]+/g, "-") || `competitor-${index}`,
          ...competitor,
        },
  ),
);

const boardInvestors = computed(() => props.company.board_investors || []);
const capTable = computed(() => props.company.cap_table_lineage || []);

function metricSource(metric) {
  const ref = Array.isArray(metric.source_refs) ? metric.source_refs[0] : null;
  if (ref?.label) return ref.label;
  if (metric.source_class && metric.as_of) return `${metric.source_class} · ${metric.as_of}`;
  return metric.source_class || "source pending";
}
</script>

<template>
  <div class="space-y-6">
    <section class="rounded-card border border-subtle bg-surface p-6 shadow-card">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div class="flex min-w-0 items-start gap-4">
          <div
            class="mono-data grid h-16 w-16 shrink-0 place-items-center rounded-glass bg-accent-soft text-xl font-bold text-accent-ink ring-1 ring-subtle"
          >
            {{ monogram(company.name) }}
          </div>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="font-display text-3xl font-bold text-ink-primary">
                {{ company.name }}
              </h2>
              <span
                v-if="company.latest_funding?.round"
                class="rounded-chip bg-surface-muted px-2 py-1 text-xs font-semibold text-ink-secondary"
              >
                {{ company.latest_funding.round }}
              </span>
              <span
                v-if="tr('industry') || tr('sector')"
                class="rounded-chip bg-accent-soft px-2 py-1 text-xs font-semibold text-accent-ink"
              >
                {{ tr("industry") || tr("sector") }}
              </span>
              <a
                v-if="websiteHref"
                :href="websiteHref"
                target="_blank"
                rel="noopener"
                class="inline-flex items-center gap-1 rounded text-xs font-semibold text-accent-ink hover:text-ink-primary focus-ring"
              >
                <ExternalLink class="h-3.5 w-3.5" />
                {{ company.website.replace(/^https?:\/\//, "") }}
              </a>
            </div>
            <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-ink-muted">
              <span v-if="company.founded_year">Founded {{ company.founded_year }}</span>
              <span v-if="tr('hq')">{{ tr("hq") }}</span>
              <span v-if="tr('employee_band')">{{ tr("employee_band") }} employees</span>
            </div>
            <div v-if="refreshError" class="mt-2 text-xs text-danger">
              {{ refreshError }}
            </div>
          </div>
        </div>

        <button
          type="button"
          @click="refresh"
          :disabled="refreshing"
          class="pill-button border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring"
        >
          <Loader2 v-if="refreshing" class="h-4 w-4 animate-spin" />
          <RefreshCw v-else class="h-4 w-4" />
          <span>{{ refreshing ? "Refreshing" : "Refresh data" }}</span>
        </button>
      </div>

      <div
        class="mt-6 rounded-card border border-subtle bg-surface-muted p-5 text-base leading-relaxed text-ink-primary"
      >
        {{ positioningText }}
      </div>
    </section>

    <section class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div
        v-for="metric in metrics"
        :key="metric.label"
        class="rounded-card border border-subtle bg-surface p-5 shadow-card"
      >
        <div class="vogue-label">{{ metric.label }}</div>
        <div class="mono-data mt-2 text-3xl font-bold text-ink-primary">
          {{ metric.value || "Unknown" }}
        </div>
        <div class="mt-2 text-[11px] leading-snug text-ink-muted">
          {{ metricSource(metric) }}
        </div>
      </div>
    </section>

    <section class="rounded-card border border-subtle bg-surface p-6 shadow-card">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="font-display text-xl font-bold text-ink-primary">Core Team</h3>
        <span class="mono-data text-xs text-ink-muted">{{ team.length }}</span>
      </div>
      <div v-if="team.length" class="grid gap-3 md:grid-cols-3">
        <article
          v-for="person in team"
          :key="`${person.name}-${person.role}`"
          class="rounded-row border border-subtle bg-surface-muted p-4"
        >
          <div class="flex items-start gap-3">
            <div
              class="mono-data grid h-10 w-10 shrink-0 place-items-center rounded-full bg-surface text-sm font-bold text-accent-ink ring-1 ring-subtle"
            >
              {{ monogram(person.name) }}
            </div>
            <div class="min-w-0">
              <div class="font-semibold text-ink-primary">{{ person.name }}</div>
              <div class="text-xs text-ink-muted">{{ person.role }}</div>
            </div>
          </div>
          <p v-if="person.bio" class="mt-3 text-sm leading-relaxed text-ink-secondary">
            {{ person.bio }}
          </p>
          <div class="mt-3 flex gap-3 text-xs font-semibold">
            <a
              v-if="person.linkedin_url"
              :href="person.linkedin_url"
              target="_blank"
              rel="noopener"
              class="text-accent-ink hover:text-ink-primary focus-ring rounded"
            >
              LinkedIn
            </a>
            <a
              v-if="person.profile_url"
              :href="person.profile_url"
              target="_blank"
              rel="noopener"
              class="text-accent-ink hover:text-ink-primary focus-ring rounded"
            >
              Profile
            </a>
          </div>
        </article>
      </div>
      <div v-else class="text-sm text-ink-muted">Team profiles pending.</div>
    </section>

    <section class="rounded-card border border-subtle bg-surface p-6 shadow-card">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="font-display text-xl font-bold text-ink-primary">
          Products
          <span class="mono-data text-sm text-ink-muted">· {{ products.length }}</span>
        </h3>
      </div>
      <div class="grid gap-3 md:grid-cols-2">
        <article
          v-for="product in products"
          :key="product.id || product.name"
          class="rounded-row border border-subtle bg-surface-muted p-4"
        >
          <div class="font-semibold text-ink-primary">{{ product.name }}</div>
          <p v-if="product.description" class="mt-2 text-sm leading-relaxed text-ink-secondary">
            {{ product.description }}
          </p>
        </article>
      </div>
    </section>

    <section class="rounded-card border border-subtle bg-surface p-6 shadow-card">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 class="font-display text-xl font-bold text-ink-primary">
          Competitors
          <span class="mono-data text-sm text-ink-muted">· {{ competitors.length }}</span>
        </h3>
        <div class="flex flex-wrap gap-2">
          <button class="pill-button border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring">
            Compare to {{ company.name.replace(/,?\s*Inc\.?$/i, "") }}
          </button>
          <button class="pill-button border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring">
            + Add competitor
          </button>
        </div>
      </div>
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="competitor in competitors"
          :key="competitor.id || competitor.name"
          class="rounded-row border border-subtle bg-surface-muted p-4"
        >
          <div class="flex items-start gap-3">
            <div
              class="mono-data grid h-10 w-10 shrink-0 place-items-center rounded-chip bg-surface text-sm font-bold text-accent-ink ring-1 ring-subtle"
            >
              {{ monogram(competitor.name) }}
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <div class="font-semibold text-ink-primary">{{ competitor.name }}</div>
                <span
                  class="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted"
                >
                  {{ competitor.status || competitor.company_type || "Private" }}
                </span>
              </div>
              <p class="mt-2 text-sm leading-relaxed text-ink-secondary">
                {{ competitor.note || competitor.description || "Comparison profile pending." }}
              </p>
              <RouterLink
                :to="{
                  name: 'competitor-detail',
                  params: {
                    companyId: company.id,
                    competitorId: competitor.id || competitor.name?.toLowerCase().replace(/[^\w]+/g, '-'),
                  },
                }"
                class="mt-3 inline-flex text-xs font-semibold text-accent-ink hover:text-ink-primary focus-ring rounded"
              >
                View profile &amp; compare →
              </RouterLink>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="grid gap-4 lg:grid-cols-2">
      <div class="rounded-card border border-subtle bg-surface p-6 shadow-card">
        <div class="vogue-label">Board · Cap Table</div>
        <h3 class="mt-1 font-display text-xl font-bold text-ink-primary">
          Board &amp; Lead Investors
        </h3>
        <div v-if="boardInvestors.length" class="mt-4 space-y-3">
          <div
            v-for="investor in boardInvestors"
            :key="`${investor.name}-${investor.role}`"
            class="flex items-start gap-3 rounded-row bg-surface-muted p-3"
          >
            <div
              class="mono-data grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface text-xs font-bold text-accent-ink ring-1 ring-subtle"
            >
              {{ monogram(investor.name) }}
            </div>
            <div class="min-w-0">
              <div class="font-semibold text-ink-primary">{{ investor.name }}</div>
              <div class="text-xs text-ink-muted">{{ investor.role || investor.affiliation }}</div>
            </div>
          </div>
        </div>
        <div v-else class="mt-4 text-sm text-ink-muted">Board records pending.</div>
      </div>

      <div class="rounded-card border border-subtle bg-surface p-6 shadow-card">
        <div class="vogue-label">Cap Table Lineage</div>
        <div v-if="capTable.length" class="mt-4 space-y-4">
          <div v-for="holder in capTable" :key="holder.name">
            <div class="mb-1 flex items-center justify-between gap-3 text-sm">
              <span class="font-semibold text-ink-primary">{{ holder.name }}</span>
              <span class="mono-data font-bold text-ink-primary">{{ holder.ownership }}</span>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-surface-muted">
              <div
                class="h-full rounded-full bg-accent"
                :style="{ width: holder.ownership || '0%' }"
              ></div>
            </div>
          </div>
        </div>
        <div v-else class="mt-4 text-sm text-ink-muted">Ownership lineage pending.</div>
      </div>
    </section>

    <TraderView
      v-if="company.company_type === 'public'"
      :company="company"
      :language="viewLang"
      @refreshed="(c) => c && $emit('refreshed', c)"
    />
  </div>
</template>
