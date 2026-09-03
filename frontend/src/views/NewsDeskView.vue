<script setup>
import { computed, inject, ref, unref } from "vue";
import { useRouter } from "vue-router";
import { companyViews, trackedCompanyIds } from "../state.js";
import { buildTickerTape, displayTicker, publicTickers } from "../liveTicker.js";
import { useLiveQuotes } from "../useLiveQuotes.js";
import { useT } from "../i18n.js";
import HomeMarketPanel from "../components/HomeMarketPanel.vue";
import HomeNewsDesk from "../components/HomeNewsDesk.vue";
import LiveTickerTape from "../components/LiveTickerTape.vue";

const emit = defineEmits(["open-copilot"]);
const t = useT();
const router = useRouter();

const companies = inject("workspaceCompanies", ref([]));
const companyList = computed(() => unref(companies) || []);

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

function followInitial(company) {
  const ticker = displayTicker(company, companyList.value);
  if (ticker) return ticker.slice(0, 2);
  return String(company.name || "?").trim().slice(0, 1).toUpperCase();
}

function followLabel(company) {
  return displayTicker(company, companyList.value) || company.name;
}

function openCompany(company) {
  router.push({ name: "research", params: { companyId: company.id } });
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
  <div class="news-page">
    <header class="news-page-header">
      <h1 class="font-display text-large-title text-ink-primary">
        {{ t("nav.news") }}
      </h1>
    </header>

    <LiveTickerTape
      v-if="tickerTape.length"
      class="mb-5"
      :items="tickerTape"
      link-to-tracking
      @select="openCompany"
    />

    <section v-if="followingCompanies.length" class="mb-6">
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

    <div class="grid items-start gap-8 lg:grid-cols-12">
      <HomeNewsDesk
        class="lg:col-span-8"
        :book-ids="bookCompanyIds"
        @open-company="openCompany"
        @open-news="openNews"
        @open-copilot="emit('open-copilot', $event)"
      />
      <HomeMarketPanel
        class="lg:col-span-4"
        :companies="companyList"
        :quotes="liveQuotes"
        @open-company="openCompany"
      />
    </div>
  </div>
</template>
