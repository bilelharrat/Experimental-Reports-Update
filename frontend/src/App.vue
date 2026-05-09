<script setup>
import { computed, onMounted, ref } from "vue";
import { api } from "./api.js";
import Sidebar from "./components/Sidebar.vue";
import ActiveJobsRail from "./components/ActiveJobsRail.vue";
import DeckSummaryModal from "./components/DeckSummaryModal.vue";
import { activeSummaryTarget, closeSummary } from "./state.js";

const reports = ref([]);
const externalFeed = ref([]);
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
    externalFeed.value = f;
    hormuz.value = h;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

onMounted(refreshAll);

// Poll so the sidebar reflects in-progress generations and analyses.
setInterval(refreshAll, 4000);

const summaryCompanyId = computed(() => activeSummaryTarget.value?.companyId);
const summaryFile = computed(() => activeSummaryTarget.value?.file ?? null);
</script>

<template>
  <div class="min-h-screen flex">
    <Sidebar
      :reports="reports"
      :external-feed="externalFeed"
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
