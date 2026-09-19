<script setup>
// Market, Pulse and News are one desk, not three.
//
// They answered the same question from different angles — what is the tape
// doing, what does the week read like, what happened — and each held its own
// sidebar entry, so the nav carried three rows for one idea and the reader
// had to leave the surface to change angle. They are tabs now.
//
// Only the selected tab is MOUNTED: MarketRadarView alone is ~3,600 lines and
// each of the three installs its own large-title scroll observer, so keeping
// all three alive would pay for two views nobody is reading and leave three
// observers fighting over one header.
//
// The tab lives in the QUERY (`/markets?tab=news`), not the path, so the
// sidebar's glider — which keys off `router-link-exact-active` — stays on the
// Markets row whichever tab is open. A path segment would drop the highlight
// the moment you switched tab.
import { computed, defineAsyncComponent } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useT } from "../i18n.js";

import MacTabBar from "../components/research/MacTabBar.vue";

// Async, matching how the router loaded these when they were three routes:
// a static import here would pull all three into one chunk and undo the
// code-splitting the app already had.
const MarketRadarView = defineAsyncComponent(
  () => import("./MarketRadarView.vue"),
);
const WeeklySummaryView = defineAsyncComponent(
  () => import("./WeeklySummaryView.vue"),
);
const NewsDeskView = defineAsyncComponent(() => import("./NewsDeskView.vue"));

const t = useT();
const route = useRoute();
const router = useRouter();

const MARKETS_TABS = ["market", "pulse", "news"];

const VIEWS = {
  market: MarketRadarView,
  pulse: WeeklySummaryView,
  news: NewsDeskView,
};

const activeTab = computed({
  get() {
    const raw = String(route.query.tab || "").trim().toLowerCase();
    return MARKETS_TABS.includes(raw) ? raw : "market";
  },
  set(value) {
    if (!MARKETS_TABS.includes(value) || value === activeTab.value) return;
    // replace, not push: flipping between tabs of one desk should not fill
    // the back button with steps the reader has to walk out of.
    router.replace({ name: "markets", query: { ...route.query, tab: value } });
  },
});

const tabItems = computed(() =>
  MARKETS_TABS.map((id) => ({ id, label: t(`markets.tab_${id}`) })),
);

const activeView = computed(() => VIEWS[activeTab.value]);
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <div class="shrink-0 px-4 pt-2 md:px-6">
      <MacTabBar v-model="activeTab" :items="tabItems" />
    </div>
    <component :is="activeView" :key="activeTab" />
  </div>
</template>
