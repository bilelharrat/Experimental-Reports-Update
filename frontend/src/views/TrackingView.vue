<script setup>
import { computed, inject, ref, unref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import {
  Loader2,
  Newspaper,
  RefreshCw,
  TrendingDown,
  TrendingUp,
} from "lucide-vue-next";
import {
  companySummaryMetrics,
  inferredMetricLabelKey,
} from "../companyMetrics.js";
import { api } from "../api.js";
import { currentLanguage, useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import {
  companyStatusLine,
  latestNewsFor,
  relatedNews,
  sortCompanies,
} from "../companyLists.js";
import {
  formatCompactNumber,
  formatIsoDate,
  formatMetricValue,
  humanizeStatus,
  isPendingValue,
} from "../formatters.js";
import {
  buildTickerTape,
  lastPriceLabel,
  publicTickers as tickersFrom,
  signedChange,
} from "../liveTicker.js";
import { radarAge, radarRoute } from "../marketRadar.js";
import { trackingActionLabel } from "../trackingLabels.js";
import { useLiveQuotes } from "../useLiveQuotes.js";
import { useTrackingRollup } from "../useTrackingRollup.js";
import CompanyFollowButton from "../components/CompanyFollowButton.vue";
import LiveTickerTape from "../components/LiveTickerTape.vue";
import TrackingAttentionStrip from "../components/TrackingAttentionStrip.vue";
import { trackedCompanyIds } from "../state.js";

const emit = defineEmits(["open-copilot"]);

const t = useT();
const router = useRouter();

const workspaceCompanies = inject("workspaceCompanies", ref([]));
const workspaceNews = inject("workspaceNews", ref([]));
const workspaceLoading = inject("workspaceLoading", ref(false));

const companyList = computed(() => unref(workspaceCompanies) || []);
const newsList = computed(() => unref(workspaceNews) || []);

const followedOnly = ref(false);
const syncingAll = ref(false);
const syncAllError = ref("");

const trackedIds = computed(() => [...trackedCompanyIds.value].map(String));
const trackedSet = computed(() => new Set(trackedIds.value));

const visibleCompanies = computed(() => {
  const rows = followedOnly.value
    ? companyList.value.filter((company) => trackedSet.value.has(String(company.id)))
    : companyList.value;
  return sortCompanies(rows, { sort: "az", favorites: trackedSet.value });
});

const visibleIds = computed(() =>
  visibleCompanies.value.map((company) => String(company.id)),
);

const publicTickers = computed(() => tickersFrom(visibleCompanies.value));
const { quotes: liveQuotes } = useLiveQuotes(publicTickers);
const { rollup, rollupError, rollupLoading, loadRollup, work } =
  useTrackingRollup(visibleIds);

async function syncAllTracked() {
  if (syncingAll.value || trackedIds.value.length === 0) return;
  syncingAll.value = true;
  syncAllError.value = "";
  try {
    await api.syncAllTrackingUpdates({
      company_ids: trackedIds.value,
      mark_auto: true,
      execute: true,
      refresh_news: true,
      lang: appLanguage.value,
    });
    await loadRollup();
  } catch (e) {
    syncAllError.value = e?.message || t("tracking.sync_all_failed");
  } finally {
    syncingAll.value = false;
  }
}
const tickerTape = computed(() =>
  buildTickerTape(visibleCompanies.value, liveQuotes.value),
);

const rollupById = computed(() => {
  const map = new Map();
  for (const row of rollup.value?.companies || []) {
    map.set(String(row.id), row);
  }
  return map;
});

function liveQuoteFor(company) {
  const ticker = String(company?.ticker || "").trim().toUpperCase();
  return ticker ? liveQuotes.value[ticker] || null : null;
}

function priceBits(row, company) {
  const live = liveQuoteFor(company);
  const card = row?.price;
  const fallback = company?.trader_snapshot?.price_card || {};
  const day = live?.change_pct_1d ?? card?.change_pct_1d ?? fallback.change_pct_1d;
  const vs = card?.vs_sp500_30d_pct ?? card?.change_pct_30d ?? fallback.vs_sp500_30d_pct;
  const last = live?.last_price ?? card?.last_price ?? fallback.last_price;
  if (day == null && vs == null && last == null) return null;
  return {
    day: day != null ? Number(day) : null,
    vs: vs != null ? Number(vs) : null,
    last: last != null ? Number(last) : null,
    currency: live?.currency || card?.currency || fallback.currency || "USD",
    live: Boolean(live && (live.last_price != null || live.change_pct_1d != null)),
  };
}

function websiteHost(company) {
  const raw = String(company.website || "").trim();
  if (!raw) return "";
  return raw.replace(/^https?:\/\//i, "").replace(/\/$/, "");
}

function factsLine(company) {
  const parts = [];
  if (company.hq) parts.push(company.hq);
  if (company.founded_year) parts.push(`${t("company.founded")} ${company.founded_year}`);
  if (company.employee_band) {
    parts.push(`${company.employee_band} ${t("company.employees")}`);
  }
  const host = websiteHost(company);
  if (host) parts.push(host);
  return parts.join(" · ");
}

function moneyBit(value) {
  if (isPendingValue(value)) return null;
  return formatCompactNumber(value, { currency: true });
}

function fundingLine(company) {
  const funding = company.latest_funding;
  if (!funding) return null;
  const parts = [];
  if (funding.round) parts.push(funding.round);
  const amount = moneyBit(funding.amount_usd);
  if (amount) parts.push(amount);
  const post = moneyBit(funding.post_money_usd);
  if (post) parts.push(`${t("company.post_money")} ${post}`);
  if (funding.lead_investor) {
    parts.push(t("company.led_by", { investor: funding.lead_investor }));
  }
  const raised = moneyBit(company.total_funding_usd);
  if (raised) parts.push(`${t("company.total_raised")} ${raised}`);
  if (funding.date) parts.push(formatIsoDate(funding.date));
  return parts.join(" · ") || null;
}

function earningsLine(company) {
  const earnings = company.latest_earnings;
  if (!earnings) return null;
  const parts = [];
  if (earnings.period) parts.push(earnings.period);
  if (earnings.revenue_yoy) {
    parts.push(t("company.revenue_yoy", { value: earnings.revenue_yoy }));
  }
  if (earnings.eps) parts.push(`EPS ${earnings.eps}`);
  if (earnings.beat_or_miss) parts.push(earnings.beat_or_miss);
  return parts.join(" · ") || null;
}

function lastEvent(company, headline) {
  const highlight = company.highlight_2026;
  if (highlight?.headline) {
    return { text: highlight.headline, date: highlight.date };
  }
  const embedded = (company.recent_news || company.company_news || [])[0];
  if (embedded) {
    return {
      text: embedded.headline || embedded.title || embedded.summary,
      date: embedded.date || embedded.published_at,
    };
  }
  if (headline?.title) return { text: headline.title, date: headline.captured_at };
  return null;
}

function peopleLine(company) {
  const people = company.team_profiles?.length
    ? company.team_profiles
    : company.key_people || [];
  return people
    .slice(0, 3)
    .map((person) => {
      const name = person.name || person;
      const role = person.role;
      return role ? `${name} (${role})` : name;
    })
    .filter(Boolean)
    .join(" · ");
}

function namedList(items, limit = 3) {
  return (items || [])
    .map((item) => (typeof item === "string" ? item : item?.name))
    .filter(Boolean)
    .slice(0, limit)
    .join(" · ");
}

function metricLabel(metric) {
  const key = metric.label_key || inferredMetricLabelKey(metric.label);
  return key ? t(key) : metric.label;
}

function realMetrics(company) {
  return companySummaryMetrics(company)
    .filter((metric) => !isPendingValue(metric.value))
    .slice(0, 4)
    .map((metric) => ({
      label: metricLabel(metric),
      value: formatMetricValue(metric.label, metric.value),
    }));
}

function coverageBits(row) {
  if (!row) return [];
  const bits = [];
  const risks = row.risks || {};
  if (risks.total) {
    bits.push(
      t("tracking.risks_ratio", {
        done: risks.researched || 0,
        total: risks.total,
      }),
    );
  }
  const evidence = row.evidence || {};
  if (evidence.total) {
    bits.push(
      t("tracking.evidence_ratio", {
        done: evidence.supported || 0,
        total: evidence.total,
      }),
    );
  }
  const newsCount = row.news?.recent_count || 0;
  if (newsCount) bits.push(t("tracking.news_recent", { count: newsCount }));
  const docs = row.documents?.total || 0;
  if (docs) bits.push(t("tracking.docs_count", { count: docs }));
  return bits;
}

const cards = computed(() =>
  visibleCompanies.value.map((company) => {
    const row = rollupById.value.get(String(company.id));
    const headline = latestNewsFor(newsList.value, company);
    const price = priceBits(row, company);
    return {
      company,
      row,
      headline,
      status: companyStatusLine(company, t),
      facts: factsLine(company),
      funding: fundingLine(company),
      earnings: earningsLine(company),
      event: lastEvent(company, headline),
      people: peopleLine(company),
      products: namedList(company.products, 3),
      competitors: namedList(
        company.competitor_cards?.length ? company.competitor_cards : company.competitors,
        3,
      ),
      metrics: realMetrics(company),
      coverage: coverageBits(row),
      price,
      lastPrice: lastPriceLabel(price),
      priceUp: price?.day != null && Number(price.day) >= 0,
      live: Boolean(price?.live),
    };
  }),
);

const boardNews = computed(() =>
  relatedNews(newsList.value, visibleCompanies.value, 10),
);

watch(
  trackedIds,
  (ids) => {
    if (ids.length === 0) followedOnly.value = false;
  },
  { deep: true },
);

function openCompany(company) {
  router.push({ name: "research", params: { companyId: company.id } });
}

function inspectAttention(item) {
  emit("open-copilot", {
    companyId: item.company_id,
    prompt: `Why is this company flagged (${item.label})? What is the fastest next step?`,
    context: {
      surface: "tracking",
      attention: {
        kind: item.kind,
        label: item.label,
        detail: item.detail,
        count: item.count,
        company_id: item.company_id,
        company_name: item.company_name,
      },
      selection: {
        company_id: item.company_id,
        company_name: item.company_name,
      },
    },
  });
}

function actionLabel(action) {
  return trackingActionLabel(action, t);
}

function memoChip(row) {
  if (!row?.memo?.total) return null;
  return humanizeStatus(row.memo.latest_status, "", currentLanguage.value);
}

function memoChipClass(row) {
  const status = row?.memo?.latest_status || "";
  if (status.startsWith("failed")) return "bg-danger/15 text-danger";
  if (status === "complete_with_warnings") return "bg-warning/15 text-warning";
  if (status.startsWith("complete")) return "bg-success/15 text-success";
  return "bg-fill-tertiary text-ink-secondary";
}

function signed(value) {
  return signedChange(value);
}
</script>

<template>
  <div class="mx-auto max-w-7xl px-6 py-8 md:px-8">
    <header class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div class="vogue-label">{{ t("sidebar.tracking") }}</div>
        <h1 class="mt-1 font-display text-title2 text-ink-primary">
          {{ t("tracking.title") }}
        </h1>
        <p class="mt-1 max-w-2xl text-footnote text-ink-muted">
          {{ t("tracking.subtitle") }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <div v-if="trackedIds.length" class="segmented">
          <button
            type="button"
            class="segmented-item focus-ring"
            :data-selected="followedOnly ? 'false' : 'true'"
            @click="followedOnly = false"
          >
            {{ t("tracking.filter_all") }}
            <span class="mono-data ml-1 text-caption1 text-ink-subtle">{{
              companyList.length
            }}</span>
          </button>
          <button
            type="button"
            class="segmented-item focus-ring"
            :data-selected="followedOnly ? 'true' : 'false'"
            @click="followedOnly = true"
          >
            {{ t("tracking.filter_followed") }}
            <span class="mono-data ml-1 text-caption1 text-ink-subtle">{{
              trackedIds.length
            }}</span>
          </button>
        </div>
        <button
          type="button"
          class="btn-bordered btn-sm focus-ring"
          :disabled="syncingAll || trackedIds.length === 0"
          @click="syncAllTracked"
        >
          <Loader2 v-if="syncingAll" class="h-3.5 w-3.5 animate-spin" />
          {{ syncingAll ? t("tracking.sync_all_running") : t("tracking.sync_all") }}
        </button>
        <button
          type="button"
          class="btn-bordered btn-sm focus-ring"
          :disabled="rollupLoading"
          @click="loadRollup"
        >
          <Loader2 v-if="rollupLoading" class="h-3.5 w-3.5 animate-spin" />
          <RefreshCw v-else class="h-3.5 w-3.5" />
          {{ t("tracking.refresh") }}
        </button>
      </div>
    </header>

    <p v-if="syncAllError" class="mb-3 text-caption1 text-danger">{{ syncAllError }}</p>

    <p
      v-if="workspaceLoading && companyList.length === 0"
      class="flex items-center gap-2 text-callout text-ink-muted"
    >
      <Loader2 class="h-4 w-4 animate-spin" />
      {{ t("common.loading") }}
    </p>

    <div
      v-else-if="followedOnly && cards.length === 0"
      class="rounded-card bg-surface p-8 text-center shadow-card"
    >
      <h2 class="font-display text-headline text-ink-primary">
        {{ t("tracking.empty_title") }}
      </h2>
      <p class="mx-auto mt-2 max-w-md text-footnote text-ink-muted">
        {{ t("tracking.empty") }}
      </p>
    </div>

    <div v-else-if="companyList.length === 0" class="rounded-card bg-surface p-8 text-center shadow-card">
      <p class="text-callout text-ink-muted">{{ t("companies.empty") }}</p>
    </div>

    <template v-else>
      <LiveTickerTape class="mb-6" :items="tickerTape" @select="openCompany" />
      <TrackingAttentionStrip class="mb-6" :items="work" @inspect="inspectAttention" />

      <p v-if="rollupError" class="mb-4 text-footnote text-danger">
        {{ t("tracking.load_failed") }}
        <button type="button" class="ml-2 text-accent hover:underline" @click="loadRollup">
          {{ t("tracking.retry") }}
        </button>
      </p>

      <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="card in cards"
          :key="card.company.id"
          class="group-card group relative flex flex-col rounded-card p-4"
          :class="
            card.row?.bucket === 'needs_action'
              ? 'ring-1 ring-danger/30'
              : ''
          "
        >
            <div class="absolute right-2 top-2">
              <CompanyFollowButton :company-id="card.company.id" hide-until-hover />
            </div>
            <button
              type="button"
              class="min-w-0 flex-1 text-left focus-ring rounded-subbox"
              @click="openCompany(card.company)"
            >
              <div class="flex items-start justify-between gap-3 pr-8">
                <div class="min-w-0">
                  <h2 class="truncate font-display text-headline text-ink-primary">
                    {{ card.company.name }}
                  </h2>
                  <p class="mt-0.5 truncate text-caption1 text-ink-muted">
                    <span v-if="card.company.ticker" class="mono-data text-ink-secondary">
                      {{ card.company.ticker }}
                    </span>
                    <span v-if="card.company.ticker && card.status"> · </span>
                    {{ card.status }}
                  </p>
                </div>
                <div v-if="card.price" class="shrink-0 text-right">
                  <p
                    v-if="card.lastPrice"
                    class="inline-flex items-center justify-end gap-1.5 mono-data text-callout text-ink-primary"
                  >
                    <span
                      v-if="card.live"
                      class="live-pulse h-1.5 w-1.5 rounded-full bg-accent"
                      :title="t('tracking.live_tape')"
                    ></span>
                    {{ card.lastPrice }}
                  </p>
                  <p
                    v-if="card.price.day != null"
                    class="mono-data text-callout font-semibold"
                    :class="card.priceUp ? 'text-success' : 'text-danger'"
                  >
                    <TrendingUp v-if="card.priceUp" class="mb-0.5 inline h-3.5 w-3.5" />
                    <TrendingDown v-else class="mb-0.5 inline h-3.5 w-3.5" />
                    {{ signed(card.price.day) }}
                  </p>
                  <p v-if="card.price.vs != null" class="text-caption1 text-ink-subtle">
                    {{ t("tracking.vs_spx") }}
                    {{ signed(card.price.vs) }}
                  </p>
                </div>
              </div>

              <p
                v-if="card.company.description"
                class="mt-2 line-clamp-2 text-footnote leading-snug text-ink-secondary"
              >
                {{ card.company.description }}
              </p>
              <p v-if="card.facts" class="mt-2 text-caption1 text-ink-muted">
                {{ card.facts }}
              </p>

              <dl
                v-if="card.metrics.length"
                class="mt-3 grid grid-cols-2 gap-x-3 gap-y-2"
              >
                <div v-for="metric in card.metrics" :key="metric.label">
                  <dt class="vogue-label">{{ metric.label }}</dt>
                  <dd class="mono-data mt-0.5 text-footnote font-semibold text-ink-primary">
                    {{ metric.value }}
                  </dd>
                </div>
              </dl>

              <p v-if="card.funding" class="mt-2 text-caption1 text-ink-muted">
                {{ t("company.last_round") }}
                <span class="mono-data text-ink-secondary">{{ card.funding }}</span>
              </p>
              <p v-if="card.earnings" class="mt-1 text-caption1 text-ink-muted">
                {{ t("company.last_earnings") }}
                <span class="text-ink-secondary">{{ card.earnings }}</span>
              </p>
              <p v-if="card.event" class="mt-2 line-clamp-2 text-footnote text-ink-primary">
                {{ card.event.text }}
                <span v-if="card.event.date" class="text-ink-subtle">
                  · {{ formatIsoDate(card.event.date, card.event.date) }}
                </span>
              </p>
              <p v-if="card.people" class="mt-2 truncate text-caption1 text-ink-muted">
                {{ card.people }}
              </p>
              <p v-if="card.products" class="mt-1 truncate text-caption1 text-ink-muted">
                {{ t("company.products") }}
                <span class="text-ink-secondary">{{ card.products }}</span>
              </p>
              <p v-if="card.competitors" class="mt-1 truncate text-caption1 text-ink-muted">
                {{ t("company.competitors") }}
                <span class="text-ink-secondary">{{ card.competitors }}</span>
              </p>
            </button>

            <div class="mt-3 flex flex-wrap items-center gap-2">
              <span
                v-if="memoChip(card.row)"
                class="rounded-pill px-2 py-0.5 text-caption1 font-medium"
                :class="memoChipClass(card.row)"
              >
                {{ memoChip(card.row) }}
              </span>
              <span
                v-for="bit in card.coverage"
                :key="bit"
                class="rounded-pill bg-fill-tertiary px-2 py-0.5 text-caption1 text-ink-secondary"
              >
                {{ bit }}
              </span>
              <RouterLink
                v-if="card.row?.next_action && card.row.bucket === 'needs_action'"
                :to="card.row.next_action.route"
                class="text-caption1 font-medium text-accent hover:underline focus-ring rounded-subbox"
              >
                {{ actionLabel(card.row.next_action) }}
              </RouterLink>
            </div>
          </article>
      </section>

      <aside class="mt-10">
        <h2 class="font-display text-headline text-ink-primary">
          {{ t("tracking.news_board") }}
        </h2>
        <p class="mt-0.5 text-caption1 text-ink-muted">
          {{ t("tracking.news_board_hint") }}
        </p>
        <div v-if="boardNews.length === 0" class="mt-3 text-footnote text-ink-muted">
          {{ t("tracking.no_news") }}
        </div>
        <div v-else class="mt-3 space-y-1">
          <RouterLink
            v-for="item in boardNews"
            :key="item.id"
            :to="radarRoute(item)"
            class="source-row focus-ring"
          >
            <Newspaper class="h-4 w-4 shrink-0 text-ink-muted" />
            <span class="min-w-0 flex-1">
              <span class="block truncate font-medium">{{ item.title }}</span>
              <span class="block text-caption1 text-ink-muted">{{
                radarAge(item.captured_at, t)
              }}</span>
            </span>
          </RouterLink>
        </div>
      </aside>
    </template>
  </div>
</template>
