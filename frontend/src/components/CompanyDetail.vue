<script setup>
import { computed, ref, watch } from "vue";
import { formatMetricValue, isPendingValue } from "../formatters.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import TraderView from "./TraderView.vue";

const props = defineProps({
  company: { type: Object, required: true },
});
const emit = defineEmits(["refreshed"]);
const t = useT();

const viewLang = ref(appLanguage.value);
watch(appLanguage, (lang) => {
  viewLang.value = lang;
});

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
          status: t("company.private"),
          note: t("company.comparison_pending"),
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

function displayMetric(metric) {
  return formatMetricValue(metric.label, metric.value);
}
</script>

<template>
  <div class="space-y-6">
    <section class="grid overflow-hidden rounded-card border border-subtle bg-surface shadow-card sm:grid-cols-2 lg:grid-cols-4">
      <div
        v-for="metric in metrics"
        :key="metric.label"
        class="border-b border-subtle p-5 last:border-b-0 sm:border-r sm:[&:nth-child(2)]:border-r-0 lg:border-b-0 lg:[&:nth-child(2)]:border-r lg:last:border-r-0"
      >
        <div class="vogue-label">{{ metric.label }}</div>
        <div
          class="mono-data mt-2 font-bold"
          :class="isPendingValue(metric.value) ? 'text-2xl text-ink-subtle' : 'text-3xl text-ink-primary'"
        >
          {{ displayMetric(metric) }}
        </div>
        <div class="mt-2 text-[11px] leading-snug text-ink-muted">
          {{ isPendingValue(metric.value) ? t("company.metric_pending") : metricSource(metric) }}
        </div>
      </div>
    </section>

    <section class="rounded-card border border-subtle bg-surface p-6 shadow-card">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="font-display text-xl font-bold text-ink-primary">{{ t("company.core_team") }}</h3>
        <span class="mono-data text-xs text-ink-muted">{{ team.length }}</span>
      </div>
      <div v-if="team.length" class="grid gap-3 md:grid-cols-3">
        <article
          v-for="person in team"
          :key="`${person.name}-${person.role}`"
          class="rounded-row border border-subtle bg-surface p-4"
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
          <p v-if="person.bio || person.note" class="mt-3 text-sm leading-relaxed text-ink-secondary">
            {{ person.bio || person.note }}
          </p>
          <div class="mt-3 flex gap-3 text-xs font-semibold">
            <a
              v-if="person.linkedin_url"
              :href="person.linkedin_url"
              target="_blank"
              rel="noopener"
              class="text-accent-ink hover:text-ink-primary focus-ring rounded"
            >
              {{ t("company.linkedin") }}
            </a>
            <a
              v-if="person.profile_url"
              :href="person.profile_url"
              target="_blank"
              rel="noopener"
              class="text-accent-ink hover:text-ink-primary focus-ring rounded"
            >
              {{ t("company.profile") }}
            </a>
          </div>
        </article>
      </div>
      <div v-else class="text-sm text-ink-muted">{{ t("company.team_pending") }}</div>
    </section>

    <section class="rounded-card border border-subtle bg-surface p-6 shadow-card">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="font-display text-xl font-bold text-ink-primary">
          {{ t("company.products") }}
          <span class="mono-data text-sm text-ink-muted">· {{ products.length }}</span>
        </h3>
      </div>
      <div class="grid gap-3 md:grid-cols-2">
        <article
          v-for="product in products"
          :key="product.id || product.name"
          class="rounded-row border border-subtle bg-surface p-4"
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
          {{ t("company.competitors") }}
          <span class="mono-data text-sm text-ink-muted">· {{ competitors.length }}</span>
        </h3>
        <div class="flex flex-wrap gap-2">
          <button class="pill-button border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring">
            {{ t("company.compare_to", { name: company.name.replace(/,?\s*Inc\.?$/i, "") }) }}
          </button>
          <button class="pill-button border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring">
            {{ t("company.add_competitor") }}
          </button>
        </div>
      </div>
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="competitor in competitors"
          :key="competitor.id || competitor.name"
          class="rounded-row border border-subtle bg-surface p-4"
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
                  {{ competitor.status || competitor.company_type || t("company.private") }}
                </span>
              </div>
              <p class="mt-2 text-sm leading-relaxed text-ink-secondary">
                {{ competitor.note || competitor.description || t("company.comparison_pending") }}
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
                {{ t("company.view_profile_compare") }} →
              </RouterLink>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="grid gap-4 lg:grid-cols-2">
      <div class="rounded-card border border-subtle bg-surface p-6 shadow-card">
        <div class="vogue-label">{{ t("company.board_cap_table") }}</div>
        <h3 class="mt-1 font-display text-xl font-bold text-ink-primary">
          {{ t("company.board_investors") }}
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
        <div v-else class="mt-4 text-sm text-ink-muted">{{ t("company.board_pending") }}</div>
      </div>

      <div class="rounded-card border border-subtle bg-surface p-6 shadow-card">
        <div class="vogue-label">{{ t("company.cap_table_lineage") }}</div>
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
        <div v-else class="mt-4 text-sm text-ink-muted">{{ t("company.ownership_pending") }}</div>
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
