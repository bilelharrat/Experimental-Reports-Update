<script setup>
import { onMounted, ref } from "vue";
import { api } from "./api.js";
import Sidebar from "./components/Sidebar.vue";

const reports = ref([]);
const loading = ref(true);
const error = ref(null);

async function refreshReports() {
  try {
    reports.value = await api.listReports();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

onMounted(refreshReports);

// Poll so the sidebar reflects in-progress generations across pages.
setInterval(refreshReports, 4000);
</script>

<template>
  <div class="min-h-screen flex">
    <Sidebar :reports="reports" :loading="loading" :error="error" />
    <main class="flex-1 min-w-0">
      <RouterView v-slot="{ Component }">
        <component :is="Component" @reports-changed="refreshReports" />
      </RouterView>
    </main>
  </div>
</template>
