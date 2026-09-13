<script setup>
import { computed, inject, ref, unref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { companyViews, trackedCompanyIds } from "../state.js";
import { buildTickerTape, displayTicker, publicTickers } from "../liveTicker.js";
import { useLiveQuotes } from "../useLiveQuotes.js";
import { useT } from "../i18n.js";
import HomeMarketPanel from "../components/HomeMarketPanel.vue";
import HomeNewsDesk from "../components/HomeNewsDesk.vue";
import LiveTickerTape from "../components/LiveTickerTape.vue";

const NEWS_LAYOUT_KEY = "bsh.newsDesk.expanded";

function loadNewsExpanded() {
  try {
    return window.localStorage.getItem(NEWS_LAYOUT_KEY) === "1";
  } catch {
    return false;
  }
}

function saveNewsExpanded(value) {
  try {
    window.localStorage.setItem(NEWS_LAYOUT_KEY, value ? "1" : "0");
  } catch {
    /* ignore quota / private mode */
  }
}

const emit = defineEmits(["open-copilot"]);
const t = useT();
const route = useRoute();
const router = useRouter();

const companies = inject("workspaceCompanies", ref([]));
const companyList = computed(() => unref(companies) || []);

const deskExpanded = ref(
  route.query.wide === "1" || route.query.wide === "true" || loadNewsExpanded(),
);

const recentCompanies = computed(() => {
  const views = companyViews.value || {};
  return [...companyList.value]
    .filter((company) => Number(views[company.id] || 0) > 0)
    .sort((a, b) => Number(views[b.id] || 0) - Number(views[a.id] || 0))
    .slice(0, 8);
});
const trackedCompanies = computed(() => {
  const raw = trackedCompanyIds.value;
  const tracked = new Set(
    raw instanceof Set
      ? [...raw].map(String)
      : Array.isArray(raw)
        ? raw.map(String)
        : [],
  );
  if (!tracked.size) return [];
  return [...companyList.value].filter((company) => tracked.has(String(company.id)));
});
const followingCompanies = computed(() => {
  const seen = new Set();
  const rows = [];
  for (const company of [...trackedCompanies.value, ...recentCompanies.value]) {
    const id = String(company.id);
    if (seen.has(id)) continue;
    seen.add(id);
    rows.push(company);
  }
  return rows;
});
const bookCompanyIds = computed(() =>
  followingCompanies.value.map((company) => String(company.id)),
);

const deskTickers = computed(() => publicTickers(companyList.value));
const { quotes: liveQuotes } = useLiveQuotes(deskTickers);
const tickerTape = computed(() =>
  buildTickerTape(companyList.value, liveQuotes.value),
);
const watchlistTape = computed(() =>
  buildTickerTape(followingCompanies.value, liveQuotes.value),
);

watch(
  () => route.query.wide,
  (value) => {
    deskExpanded.value = value === "1" || value === "true" || loadNewsExpanded();
  },
);

function toggleDeskExpanded() {
  deskExpanded.value = !deskExpanded.value;
  saveNewsExpanded(deskExpanded.value);
  const query = { ...route.query };
  if (deskExpanded.value) query.wide = "1";
  else delete query.wide;
  router.replace({ query });
}

function followInitial(company) {
  const ticker = displayTicker(company, companyList.value);
  if (ticker) return ticker.slice(0, 2);
  return String(company.name || "?").trim().slice(0, 1).toUpperCase();
}

function followLabel(company) {
  return displayTicker(company, companyList.value) || company.name;
}

function openCompany(company) {
  if (!company) return;
  const ticker =
    String(company.ticker || "").trim().toUpperCase() ||
    displayTicker(company, companyList.value);
  if (ticker) {
    router.push({ name: "market-radar", query: { ticker } });
    return;
  }
  if (company.id) {
    router.push({ name: "research", params: { companyId: company.id } });
  }
}

function openNews(row) {
  if (row?.kind === "news" && row.raw?.id) {
    router.push({ name: "external-news", params: { id: row.raw.id } });
    return;
  }
  if (row?.kind === "external_research" && row.raw?.id) {
    router.push({ name: "external-research", params: { id: row.raw.id } });
    return;
  }
  if (row?.url && typeof window !== "undefined") {
    window.open(row.url, "_blank", "noopener");
  }
}
</script>

<template>
  <div class="news-page" :data-expanded="deskExpanded ? 'true' : 'false'">
    <header class="news-page-header">
      <h1 class="font-display text-large-title text-ink-primary">
        {{ t("nav.news") }}
      </h1>
    </header>

    <div class="mb-5 space-y-2">
      <LiveTickerTape
        v-if="tickerTape.length"
        :items="tickerTape"
        link-to-tracking
        @select="openCompany"
      />
      <LiveTickerTape
        v-if="deskExpanded && watchlistTape.length"
        :items="watchlistTape"
        :label="t('home.desk_movers')"
        link-to-tracking
        @select="openCompany"
      />
    </div>

    <section v-if="!deskExpanded && followingCompanies.length" class="mb-6">
      <h2 class="mb-3 px-1 font-display text-title2 text-ink-primary">
        {{ t("home.desk_following") }}
      </h2>
      <div class="news-follow-row">
        <button
          v-for="company in followingCompanies"
          :key="company.id"
          type="button"
          class="news-follow-chip focus-ring"
          @click="openCompany(company)"
        >
          <span class="news-follow-avatar">{{ followInitial(company) }}</span>
          <span class="max-w-[4.5rem] truncate text-caption1 font-medium text-ink-secondary">
            {{ followLabel(company) }}
          </span>
        </button>
      </div>
    </section>

    <div
      :class="
        deskExpanded
          ? 'space-y-6'
          : 'grid items-start gap-8 lg:grid-cols-12'
      "
    >
      <HomeNewsDesk
        :class="deskExpanded ? '' : 'lg:col-span-8'"
        :book-ids="bookCompanyIds"
        :expanded="deskExpanded"
        @toggle-expand="toggleDeskExpanded"
        @open-company="openCompany"
        @open-news="openNews"
        @open-copilot="emit('open-copilot', $event)"
      />
      <HomeMarketPanel
        v-if="!deskExpanded"
        class="lg:col-span-4"
        :companies="companyList"
        :quotes="liveQuotes"
        @open-company="openCompany"
      />
    </div>
  </div>
</template>
