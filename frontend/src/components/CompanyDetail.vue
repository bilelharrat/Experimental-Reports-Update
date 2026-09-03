<script setup>
import { computed, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import {
  companyMetricHistories,
  companySummaryMetrics,
  inferredMetricLabelKey,
  inferredMetricSourceKey,
} from "../companyMetrics.js";
import { formatIsoDate, formatMetricValue, isPendingValue } from "../formatters.js";
import { TARGET_KINDS } from "../copilotTargets.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import CopilotDropZone from "./CopilotDropZone.vue";
import TraderView from "./TraderView.vue";

const props = defineProps({
  company: { type: Object, required: true },
  latestAutoRun: { type: Object, default: null },
  trackingUpdates: { type: Object, default: null },
});
const emit = defineEmits(["refreshed"]);
const t = useT();
const router = useRouter();
const addingCompetitor = ref(false);
const newCompetitorName = ref("");
const expandedPeople = ref(new Set());

const viewLang = ref(appLanguage.value);
watch(appLanguage, (lang) => {
  viewLang.value = lang;
});

const resolvedAutoRun = computed(
  () => props.latestAutoRun || props.trackingUpdates?.latest_auto_run || null,
);

const showAutoUpdatedBadge = computed(() => {
  const run = resolvedAutoRun.value;
  if (!run) return false;
  const surface = String(run.surface || "").toLowerCase();
  const action = String(run.action || run.recommended_action || "").toLowerCase();
  return surface === "overview" || action === "deep_investigate";
});

const autoUpdatedLabel = computed(() => {
  const label = String(resolvedAutoRun.value?.label || "").trim();
  if (!label) return "";
  return label.length > 40 ? `${label.slice(0, 40)}…` : label;
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

const metrics = computed(() => companySummaryMetrics(props.company));
const metricHistories = computed(() => companyMetricHistories(props.company));
const hasInvestigationContext = computed(() => {
  const c = props.company || {};
  return Boolean(
    (Array.isArray(c.metrics) && c.metrics.length)
      || c.metric_history?.length
      || c.latest_earnings
      || c.trader_snapshot
      || (Array.isArray(c.team_profiles) && c.team_profiles.some((p) => p?.achievements || p?.rating)),
  );
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
  if (ref?.label) {
    const sourceKey = ref.label_key || inferredMetricSourceKey(ref.label);
    return viewLang.value === "zh" && sourceKey ? t(sourceKey) : ref.label;
  }
  const sourceLabel = metric.source_key ? t(metric.source_key) : metric.source_class;
  if (sourceLabel && metric.as_of) {
    const rawDate = String(metric.as_of).match(
      /(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}/,
    )?.[0];
    const normalizedDate = rawDate
      ? formatIsoDate(new Date(rawDate).toISOString())
      : formatIsoDate(metric.as_of, viewLang.value === "zh" ? "" : metric.as_of);
    return normalizedDate ? `${sourceLabel} · ${normalizedDate}` : sourceLabel;
  }
  return sourceLabel || t("company.metric_pending");
}

function metricLabel(metric) {
  if (viewLang.value === "zh" && metric.label_zh) return metric.label_zh;
  const labelKey = metric.label_key || inferredMetricLabelKey(metric.label);
  return viewLang.value === "zh" && labelKey ? t(labelKey) : metric.label;
}

function displayMetric(metric) {
  return formatMetricValue(metric.label, metric.value);
}

function historyLabel(series) {
  if (viewLang.value === "zh" && series.label_key) return t(series.label_key);
  return series.label;
}

function sparklinePoints(series) {
  const values = series.points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 220;
  const height = 64;
  return series.points
    .map((point, index) => {
      const x = (index / Math.max(series.points.length - 1, 1)) * width;
      const y = height - ((point.value - min) / span) * (height - 8) - 4;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function personKey(person) {
  return `${person.name}-${person.role || ""}`;
}

function personExpanded(person) {
  return expandedPeople.value.has(personKey(person));
}

function togglePerson(person) {
  const key = personKey(person);
  const next = new Set(expandedPeople.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedPeople.value = next;
}

function personAchievements(person) {
  const rows = person.achievements || person.highlights || person.successes || [];
  if (Array.isArray(rows)) return rows.map((row) => (typeof row === "string" ? row : row?.text || row?.title)).filter(Boolean);
  if (typeof rows === "string") return [rows];
  return [];
}

function personRating(person) {
  const value = person.rating ?? person.score ?? person.founder_score;
  if (value == null || value === "") return null;
  return value;
}

function competitorId(competitor) {
  return (
    competitor.id ||
    competitor.name?.toLowerCase().replace(/[^\w]+/g, "-") ||
    "competitor"
  );
}

function openCompetitor(competitor) {
  if (!competitor) return;
  router.push({
    name: "competitor-detail",
    params: {
      companyId: props.company.id,
      competitorId: competitorId(competitor),
    },
  });
}

function submitNewCompetitor() {
  const name = newCompetitorName.value.trim();
  if (!name) return;
  openCompetitor({
    id: name.toLowerCase().replace(/[^\w]+/g, "-"),
    name,
  });
  addingCompetitor.value = false;
  newCompetitorName.value = "";
}

function onTraderRefreshed(company) {
  if (company) emit("refreshed", company);
}
</script>

<template>
  <div class="space-y-6">
    <section class="group-card overflow-hidden">
      <div class="grid sm:grid-cols-2 lg:grid-cols-4">
        <CopilotDropZone
          v-for="metric in metrics"
          :key="metric.label"
          :company-id="company.id"
          surface="overview"
          tab="overview"
          :target-kind="TARGET_KINDS.METRIC"
          :target-id="metric.label"
          block
          :selection="{
            metric_label: metricLabel(metric),
            metric_value: displayMetric(metric),
            as_of: metric.as_of,
            source_class: metric.source_class,
            source_refs: metric.source_refs || [],
          }"
          class="border-b border-subtle p-4 last:border-b-0 sm:border-r sm:[&:nth-child(2)]:border-r-0 lg:border-b-0 lg:[&:nth-child(2)]:border-r lg:last:border-r-0"
        >
          <div class="vogue-label">{{ metricLabel(metric) }}</div>
          <div
            class="mono-data mt-1.5 font-semibold tracking-tight"
            :class="isPendingValue(metric.value) ? 'text-title3 text-ink-subtle' : 'text-title2 text-ink-primary'"
          >
            {{ displayMetric(metric) }}
          </div>
          <div class="mt-1 text-caption1 leading-snug text-ink-muted">
            {{ isPendingValue(metric.value) ? t("company.metric_pending") : metricSource(metric) }}
          </div>
        </CopilotDropZone>
      </div>

      <div class="hairline-t px-4 py-4">
        <div class="flex items-baseline justify-between gap-3">
          <h3 class="text-footnote font-semibold text-ink-secondary">
            {{ t("company.metric_trends") }}
          </h3>
          <div class="flex items-center gap-2">
            <span
              v-if="showAutoUpdatedBadge"
              class="rounded-full border border-accent/30 bg-accent-soft/50 px-2 py-0.5 text-[10px] font-semibold text-accent-ink"
              :title="autoUpdatedLabel || t('company.auto_updated')"
            >
              {{ t("company.auto_updated") }}
              <span v-if="autoUpdatedLabel" class="font-medium text-ink-muted">
                · {{ autoUpdatedLabel }}
              </span>
            </span>
            <span class="mono-data text-caption1 text-ink-subtle">
              {{ metricHistories.length || 0 }}
            </span>
          </div>
        </div>
        <div v-if="metricHistories.length" class="mt-3 grid gap-3 sm:grid-cols-2">
          <article
            v-for="series in metricHistories"
            :key="series.id"
            class="rounded-subbox bg-fill-tertiary p-3"
          >
            <div class="text-caption1 font-semibold text-ink-secondary">
              {{ historyLabel(series) }}
            </div>
            <svg
              class="mt-2 w-full text-accent"
              viewBox="0 0 220 64"
              role="img"
              :aria-label="historyLabel(series)"
            >
              <polyline
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                :points="sparklinePoints(series)"
              />
            </svg>
            <div class="mt-1 flex justify-between text-[11px] text-ink-muted">
              <span>{{ series.points[0]?.label }}</span>
              <span>{{ series.points[series.points.length - 1]?.label }}</span>
            </div>
          </article>
        </div>
        <p v-else class="mt-2 text-footnote text-ink-muted">
          {{ t("company.more_info_required") }}
        </p>
      </div>

      <div v-if="team.length" class="hairline-t">
        <div class="flex items-baseline justify-between gap-3 px-4 pb-1 pt-3">
          <h3 class="text-footnote font-semibold text-ink-secondary">{{ t("company.core_team") }}</h3>
          <div class="flex items-center gap-2">
            <span
              v-if="showAutoUpdatedBadge"
              class="rounded-full border border-accent/30 bg-accent-soft/50 px-2 py-0.5 text-[10px] font-semibold text-accent-ink"
              :title="autoUpdatedLabel || t('company.auto_updated')"
            >
              {{ t("company.auto_updated") }}
              <span v-if="autoUpdatedLabel" class="font-medium text-ink-muted">
                · {{ autoUpdatedLabel }}
              </span>
            </span>
            <span class="mono-data text-caption1 text-ink-subtle">{{ team.length }}</span>
          </div>
        </div>
        <ul>
          <li
            v-for="person in team"
            :key="`${person.name}-${person.role}`"
            class="px-4 py-2.5 hairline-t"
          >
            <div class="flex items-start gap-3">
              <div
                class="mono-data mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-fill-tertiary text-caption1 font-semibold text-ink-secondary"
              >
                {{ monogram(person.name) }}
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-baseline justify-between gap-x-3">
                  <div class="font-medium text-ink-primary">{{ person.name }}</div>
                  <div class="text-footnote text-ink-muted">{{ person.role }}</div>
                </div>
                <p v-if="person.bio || person.note" class="mt-0.5 text-footnote leading-relaxed text-ink-secondary">
                  {{ person.bio || person.note }}
                </p>
                <div class="mt-1 flex flex-wrap items-center gap-3 text-caption1 font-medium">
                  <a
                    v-if="person.linkedin_url"
                    :href="person.linkedin_url"
                    target="_blank"
                    rel="noopener"
                    class="rounded text-accent-ink hover:text-ink-primary focus-ring"
                  >
                    {{ t("company.linkedin") }}
                  </a>
                  <a
                    v-if="person.profile_url"
                    :href="person.profile_url"
                    target="_blank"
                    rel="noopener"
                    class="rounded text-accent-ink hover:text-ink-primary focus-ring"
                  >
                    {{ t("company.profile") }}
                  </a>
                  <button
                    type="button"
                    class="rounded text-accent-ink hover:text-ink-primary focus-ring"
                    @click="togglePerson(person)"
                  >
                    {{ personExpanded(person) ? t("company.collapse_founder") : t("company.expand_founder") }}
                  </button>
                </div>
                <div v-if="personExpanded(person)" class="mt-2 rounded-subbox bg-fill-tertiary p-3">
                  <div v-if="personRating(person) != null" class="text-caption1 font-semibold text-ink-secondary">
                    {{ t("company.founder_rating") }}:
                    <span class="mono-data text-ink-primary">{{ personRating(person) }}</span>
                  </div>
                  <ul v-if="personAchievements(person).length" class="mt-2 space-y-1">
                    <li
                      v-for="item in personAchievements(person)"
                      :key="item"
                      class="text-footnote leading-relaxed text-ink-secondary"
                    >
                      {{ item }}
                    </li>
                  </ul>
                  <p v-else class="mt-1 text-footnote text-ink-muted">
                    {{ t("company.more_info_required") }}
                  </p>
                </div>
              </div>
            </div>
          </li>
        </ul>
      </div>
      <div v-else class="hairline-t px-4 py-3 text-footnote text-ink-muted">
        {{ hasInvestigationContext ? t("company.team_pending") : t("company.more_info_required") }}
      </div>

      <div v-if="products.length" class="hairline-t">
        <div class="flex items-baseline justify-between px-4 pb-1 pt-3">
          <h3 class="text-footnote font-semibold text-ink-secondary">{{ t("company.products") }}</h3>
          <span class="mono-data text-caption1 text-ink-subtle">{{ products.length }}</span>
        </div>
        <ul>
          <li
            v-for="product in products"
            :key="product.id || product.name"
            class="px-4 py-2.5 hairline-t"
          >
            <div class="font-medium text-ink-primary">{{ product.name }}</div>
            <p v-if="product.description" class="mt-0.5 text-footnote leading-relaxed text-ink-secondary">
              {{ product.description }}
            </p>
          </li>
        </ul>
      </div>

      <div class="hairline-t">
        <div class="flex flex-wrap items-center justify-between gap-2 px-4 pb-1 pt-3">
          <h3 class="text-footnote font-semibold text-ink-secondary">
            {{ t("company.competitors") }}
            <span class="mono-data text-caption1 font-normal text-ink-subtle">{{ competitors.length }}</span>
          </h3>
          <div class="flex flex-wrap items-center gap-2">
            <button
              v-if="competitors.length"
              type="button"
              class="rounded text-caption1 font-medium text-accent-ink focus-ring"
              @click="openCompetitor(competitors[0])"
            >
              {{ t("company.compare_to", { name: competitors[0].name }) }}
            </button>
            <button
              v-if="!addingCompetitor"
              type="button"
              class="rounded text-caption1 font-medium text-accent-ink focus-ring"
              @click="addingCompetitor = true"
            >
              {{ t("company.add_competitor") }}
            </button>
            <form
              v-else
              class="flex items-center gap-1.5"
              @submit.prevent="submitNewCompetitor"
            >
              <input
                v-model="newCompetitorName"
                type="text"
                class="field h-7 w-40 py-0 text-caption1"
                :placeholder="t('company.add_competitor_name')"
                autofocus
              />
              <button type="submit" class="text-caption1 font-medium text-accent-ink focus-ring rounded">
                {{ t("company.add_competitor_go") }}
              </button>
            </form>
          </div>
        </div>
        <ul v-if="competitors.length">
          <li
            v-for="competitor in competitors"
            :key="competitor.id || competitor.name"
            class="flex items-start gap-3 px-4 py-2.5 hairline-t"
          >
            <div
              class="mono-data mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-chip bg-fill-tertiary text-caption1 font-semibold text-ink-secondary"
            >
              {{ monogram(competitor.name) }}
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-baseline justify-between gap-x-3">
                <div class="font-medium text-ink-primary">{{ competitor.name }}</div>
                <span class="text-caption1 text-ink-muted">
                  {{ competitor.status || competitor.company_type || t("company.private") }}
                </span>
              </div>
              <p class="mt-0.5 text-footnote leading-relaxed text-ink-secondary">
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
                class="mt-1 inline-flex rounded text-caption1 font-medium text-accent-ink hover:text-ink-primary focus-ring"
              >
                {{ t("company.view_profile_compare") }}
              </RouterLink>
            </div>
          </li>
        </ul>
        <p v-else class="px-4 py-2.5 text-footnote text-ink-muted">{{ t("company.comparison_pending") }}</p>
      </div>

      <div v-if="boardInvestors.length || capTable.length" class="grid hairline-t lg:grid-cols-2">
        <div v-if="boardInvestors.length" class="lg:border-r lg:border-subtle">
          <div class="px-4 pb-1 pt-3">
            <div class="vogue-label">{{ t("company.board_cap_table") }}</div>
            <h3 class="text-footnote font-semibold text-ink-secondary">{{ t("company.board_investors") }}</h3>
          </div>
          <ul>
            <li
              v-for="investor in boardInvestors"
              :key="`${investor.name}-${investor.role}`"
              class="flex items-center gap-3 px-4 py-2.5 hairline-t"
            >
              <div
                class="mono-data grid h-8 w-8 shrink-0 place-items-center rounded-full bg-fill-tertiary text-caption1 font-semibold text-ink-secondary"
              >
                {{ monogram(investor.name) }}
              </div>
              <div class="min-w-0">
                <div class="font-medium text-ink-primary">{{ investor.name }}</div>
                <div class="text-caption1 text-ink-muted">{{ investor.role || investor.affiliation }}</div>
              </div>
            </li>
          </ul>
        </div>
        <div v-if="capTable.length">
          <div class="px-4 pb-1 pt-3">
            <div class="vogue-label">{{ t("company.cap_table_lineage") }}</div>
          </div>
          <ul>
            <li v-for="holder in capTable" :key="holder.name" class="px-4 py-2.5 hairline-t">
              <div class="mb-1.5 flex items-center justify-between gap-3 text-callout">
                <span class="font-medium text-ink-primary">{{ holder.name }}</span>
                <span class="mono-data font-semibold text-ink-primary">{{ holder.ownership }}</span>
              </div>
              <div class="h-1.5 overflow-hidden rounded-full bg-fill-tertiary">
                <div
                  class="h-full rounded-full bg-accent"
                  :style="{ width: holder.ownership || '0%' }"
                ></div>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </section>

    <TraderView
      v-if="company.company_type === 'public'"
      :company="company"
      :language="viewLang"
      @refreshed="onTraderRefreshed"
    />
  </div>
</template>
