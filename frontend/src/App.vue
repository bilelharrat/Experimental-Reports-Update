<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { api } from "./api.js";
import Sidebar from "./components/Sidebar.vue";
import ActiveJobsRail from "./components/ActiveJobsRail.vue";
import DeckSummaryModal from "./components/DeckSummaryModal.vue";
import { activeSummaryTarget, closeSummary } from "./state.js";
import { isAuthenticated } from "./auth.js";

const reports = ref([]);
const news = ref([]);
const externalResearch = ref([]);
const hormuz = ref([]);
const loading = ref(true);
const error = ref(null);

async function refreshAll() {
  try {
    const [r, f, h] = await Promise.all([
      api.listReports(),
      api.externalFeed(),
      api.listHormuz(),
    ]);
    reports.value = r;
    news.value = f.filter((it) => it.kind === "news");
    externalResearch.value = f.filter((it) => it.kind === "external_research");
    hormuz.value = h;
  } catch (e) {
    // A 401 here means the session was already invalidated by auth.js
    // (which clears state + redirects via the router watcher) — don't
    // surface that as an in-page error.
    if (e?.status !== 401) error.value = e.message;
  } finally {
    loading.value = false;
  }
}

// Drive the sidebar polling off the auth state: start when we log in,
// stop when we log out. Avoids the login page making /api/* calls that
// would 401 and dispatch the unauthorized event in a loop.
let pollTimer = null;
function startPolling() {
  if (pollTimer != null) return;
  refreshAll();
  pollTimer = window.setInterval(refreshAll, 4000);
}
function stopPolling() {
  if (pollTimer != null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  reports.value = [];
  news.value = [];
  externalResearch.value = [];
  hormuz.value = [];
  loading.value = true;
  error.value = null;
}

watch(
  isAuthenticated,
  (signedIn) => {
    if (signedIn) startPolling();
    else stopPolling();
  },
  { immediate: true },
);

onBeforeUnmount(stopPolling);

const summaryCompanyId = computed(() => activeSummaryTarget.value?.companyId);
const summaryFile = computed(() => activeSummaryTarget.value?.file ?? null);
</script>

<template>
  <!-- Unauthenticated: just the routed view (LoginView). No sidebar,
       no polling, no modals. -->
  <RouterView v-if="!isAuthenticated" />

  <!-- Authenticated: full app chrome. -->
  <div v-else class="min-h-screen flex flex-col lg:flex-row">
    <Sidebar
      :reports="reports"
      :news="news"
      :external-research="externalResearch"
      :hormuz="hormuz"
      :loading="loading"
      :error="error"
    />
    <main class="flex-1 min-w-0">
      <RouterView v-slot="{ Component }">
        <component :is="Component" @reports-changed="refreshAll" />
      </RouterView>
    </main>

    <ActiveJobsRail />
    <DeckSummaryModal
      v-if="summaryCompanyId"
      :company-id="summaryCompanyId"
      :file="summaryFile"
      @close="closeSummary"
    />
  </div>
</template>
