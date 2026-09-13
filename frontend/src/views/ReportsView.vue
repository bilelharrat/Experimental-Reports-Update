<script setup>
import { computed, inject, onMounted, ref, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Clock,
  Download,
  Eye,
  FileCheck,
  FileSpreadsheet,
  FileText,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-vue-next";
import { api, withApiToken } from "../api.js";
import { useT } from "../i18n.js";
import DocumentViewerWindow from "../components/DocumentViewerWindow.vue";
import DocumentViewerDrawer from "../components/DocumentViewerDrawer.vue";

const t = useT();
const route = useRoute();
const router = useRouter();

// Optional workspaceCompanies injected from App.vue
const workspaceCompanies = inject("workspaceCompanies", ref([]));

const reports = ref([]);
const loading = ref(true);
const error = ref(null);
const searchQuery = ref(String(route.query.q || ""));
const selectedCompany = ref(String(route.query.company || "all"));
const selectedStatus = ref("all");
const selectedKind = ref("all");
const selectedReportId = ref(String(route.query.id || ""));

// Fullscreen drawer state
const drawerState = ref({
  open: false,
  title: "",
  sources: [],
});

function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function fmtTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function reportKindLabel(kind) {
  if (!kind) return "Investment Memo";
  const map = {
    investment_memo_late_stage: "Late-Stage Memo",
    buffett_memo: "Buffett Memo",
    hormuz_appendix: "Hormuz Appendix",
    memo_late_stage: "Late-Stage Memo",
    memo_buffett: "Buffett Memo",
  };
  if (map[kind]) return map[kind];
  return String(kind)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function normalizeStatus(status) {
  const s = String(status || "").toLowerCase();
  if (s === "complete" || s === "ready") return "complete";
  if (s.includes("running") || s === "queued" || s === "investigating" || s === "generating") {
    return "running";
  }
  if (s.includes("warn") || s === "cards_ready" || s === "awaiting_studio") {
    return "needs_attention";
  }
  if (s.includes("fail") || s === "error") {
    return "failed";
  }
  return "complete";
}

function reportSources(report) {
  if (!report) return [];
  const order = { en: 0, zh: 1, internal: 2 };
  const rawUrls = report.download_urls || {};
  return Object.keys(rawUrls)
    .sort((a, b) => (order[a] ?? 9) - (order[b] ?? 9))
    .map((key) => ({
      key: String(key).toUpperCase(),
      url: rawUrls[key],
      kind: "docx",
    }));
}

async function loadReports() {
  loading.value = true;
  error.value = null;
  try {
    const list = await api.listReports();
    reports.value = Array.isArray(list) ? list : [];
    // If no report selected or selected report not in list, pick the first valid one
    if (!selectedReportId.value && reports.value.length > 0) {
      const firstReady = reports.value.find(
        (r) => normalizeStatus(r.status) === "complete" && Object.keys(r.download_urls || {}).length > 0,
      );
      selectedReportId.value = firstReady ? firstReady.id : reports.value[0].id;
    }
  } catch (e) {
    error.value = e.message || "Failed to load reports";
  } finally {
    loading.value = false;
  }
}

// Available companies filter list
const companyOptions = computed(() => {
  const map = new Map();
  for (const r of reports.value) {
    if (r.company_id) {
      map.set(r.company_id, r.company_name || r.company_id);
    }
  }
  return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
});

// Available report kinds filter list
const kindOptions = computed(() => {
  const set = new Set();
  for (const r of reports.value) {
    if (r.kind || r.report_type) {
      set.add(r.kind || r.report_type);
    }
  }
  return Array.from(set).map((k) => ({ id: k, label: reportKindLabel(k) }));
});

// Filtered reports
const filteredReports = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  const company = selectedCompany.value;
  const status = selectedStatus.value;
  const kind = selectedKind.value;

  return reports.value.filter((r) => {
    if (company !== "all" && r.company_id !== company) return false;
    if (status !== "all" && normalizeStatus(r.status) !== status) return false;
    if (kind !== "all" && (r.kind !== kind && r.report_type !== kind)) return false;

    if (q) {
      const matchName = String(r.company_name || "").toLowerCase().includes(q);
      const matchId = String(r.company_id || "").toLowerCase().includes(q);
      const matchTitle = String(r.title || "").toLowerCase().includes(q);
      const matchKind = String(r.kind || "").toLowerCase().includes(q);
      if (!matchName && !matchId && !matchTitle && !matchKind) return false;
    }
    return true;
  });
});

// Currently selected report object
const activeReport = computed(() => {
  return reports.value.find((r) => r.id === selectedReportId.value) || null;
});

// Sources for active report
const activeSources = computed(() => {
  return reportSources(activeReport.value);
});

// Summary counters
const stats = computed(() => {
  let complete = 0;
  let running = 0;
  let attention = 0;
  let failed = 0;
  for (const r of reports.value) {
    const s = normalizeStatus(r.status);
    if (s === "complete") complete++;
    else if (s === "running") running++;
    else if (s === "needs_attention") attention++;
    else if (s === "failed") failed++;
  }
  return {
    total: reports.value.length,
    complete,
    running,
    attention,
    failed,
  };
});

function selectReport(report) {
  selectedReportId.value = report.id;
  router.replace({
    query: {
      ...route.query,
      id: report.id,
    },
  });
}

function openFullscreenDrawer({ title, sources }) {
  drawerState.value = {
    open: true,
    title,
    sources,
  };
}

function closeFullscreenDrawer() {
  drawerState.value.open = false;
}

watch(
  () => route.query.id,
  (newId) => {
    if (newId && newId !== selectedReportId.value) {
      selectedReportId.value = String(newId);
    }
  },
);

watch(filteredReports, (newFiltered) => {
  if (newFiltered.length > 0) {
    const stillPresent = newFiltered.some((r) => r.id === selectedReportId.value);
    if (!stillPresent) {
      selectedReportId.value = newFiltered[0].id;
    }
  } else {
    selectedReportId.value = "";
  }
});

onMounted(loadReports);
</script>

<template>
  <div class="flex h-[calc(100vh-3.25rem)] w-full flex-col overflow-hidden bg-canvas">
    <!-- Sleek Compact Header / Filter Toolbar (Single Row) -->
    <header class="flex flex-wrap items-center justify-between gap-2.5 border-b border-subtle bg-surface px-4 py-2 shrink-0">
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-2">
          <FileSpreadsheet class="h-4 w-4 text-accent" />
          <h1 class="font-display text-sm font-bold tracking-tight text-ink-primary">
            {{ t("reports.title") }}
          </h1>
        </div>
        <span class="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2.5 py-0.5 text-[11px] font-medium text-ink-secondary border border-subtle">
          {{ t("reports.total_count", { count: stats.total }) }}
        </span>
        <span
          v-if="stats.running > 0"
          class="inline-flex items-center gap-1 rounded-full bg-info-soft px-2 py-0.5 text-[11px] font-medium text-info-ink"
        >
          <Loader2 class="h-3 w-3 animate-spin" />
          {{ stats.running }} {{ t("reports.status_running") }}
        </span>
      </div>

      <!-- Controls & Filters Bar -->
      <div class="flex flex-wrap items-center gap-2">
        <!-- Search input -->
        <div class="relative w-44 sm:w-56 lg:w-64">
          <Search class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted" />
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="t('reports.search_placeholder')"
            class="h-7 w-full rounded border border-subtle bg-surface py-1 pl-8 pr-2.5 text-xs text-ink-primary placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>

        <!-- Company Filter -->
        <select
          v-model="selectedCompany"
          class="h-7 rounded border border-subtle bg-surface py-1 pl-2 pr-6 text-xs text-ink-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        >
          <option value="all">{{ t("reports.filter_company") }}</option>
          <option v-for="c in companyOptions" :key="c.id" :value="c.id">
            {{ c.name }}
          </option>
        </select>

        <!-- Kind Filter -->
        <select
          v-if="kindOptions.length > 1"
          v-model="selectedKind"
          class="h-7 rounded border border-subtle bg-surface py-1 pl-2 pr-6 text-xs text-ink-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        >
          <option value="all">{{ t("reports.filter_kind") }}</option>
          <option v-for="k in kindOptions" :key="k.id" :value="k.id">
            {{ k.label }}
          </option>
        </select>

        <!-- Status Filter -->
        <select
          v-model="selectedStatus"
          class="h-7 rounded border border-subtle bg-surface py-1 pl-2 pr-6 text-xs text-ink-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        >
          <option value="all">{{ t("reports.filter_status") }}</option>
          <option value="complete">{{ t("reports.status_complete") }}</option>
          <option value="running">{{ t("reports.status_running") }}</option>
          <option value="needs_attention">{{ t("reports.status_needs_attention") }}</option>
          <option value="failed">{{ t("reports.status_failed") }}</option>
        </select>

        <!-- Refresh Button -->
        <button
          type="button"
          class="inline-flex h-7 items-center gap-1 rounded border border-subtle bg-surface px-2.5 text-xs font-medium text-ink-primary hover:bg-surface-muted focus-ring"
          :disabled="loading"
          @click="loadReports"
        >
          <RefreshCw class="h-3 w-3" :class="{ 'animate-spin': loading }" />
          <span class="hidden sm:inline">{{ t("pulse.refresh") }}</span>
        </button>
      </div>
    </header>

    <!-- Error Banner -->
    <div
      v-if="error"
      class="flex items-center gap-3 border-b border-danger/30 bg-danger/10 px-4 py-2 text-xs text-danger shrink-0"
    >
      <AlertCircle class="h-4 w-4 shrink-0" />
      <div class="flex-1">{{ error }}</div>
      <button
        type="button"
        class="font-semibold underline hover:no-underline"
        @click="loadReports"
      >
        {{ t("research.retry") }}
      </button>
    </div>

    <!-- Main Edge-to-Edge Master-Detail Workspace -->
    <div class="flex flex-1 overflow-hidden w-full min-h-0">
      <!-- Master List (Left Pane) -->
      <aside class="w-80 lg:w-96 xl:w-[380px] shrink-0 border-r border-subtle flex flex-col bg-surface overflow-hidden">
        <div class="flex items-center justify-between border-b border-subtle/50 px-3 py-1.5 text-[11px] text-ink-muted bg-surface-muted/30 shrink-0">
          <span class="font-medium">
            {{ t("reports.total_count", { count: filteredReports.length }) }}
          </span>
        </div>

        <!-- Loading State -->
        <div
          v-if="loading"
          class="flex flex-1 flex-col items-center justify-center p-6 text-center text-xs text-ink-muted"
        >
          <Loader2 class="h-5 w-5 animate-spin text-accent mb-2" />
          <p>{{ t("documents.viewer_loading") }}</p>
        </div>

        <!-- Empty State -->
        <div
          v-else-if="!filteredReports.length"
          class="flex flex-1 flex-col items-center justify-center p-6 text-center text-ink-muted"
        >
          <FileText class="h-7 w-7 text-ink-subtle mb-1.5" />
          <div class="text-xs font-semibold text-ink-primary">{{ t("reports.empty_title") }}</div>
          <p class="mt-1 text-[11px] text-ink-muted max-w-xs">{{ t("reports.empty_desc") }}</p>
        </div>

        <!-- Scrollable Report Cards List -->
        <div v-else class="flex-1 overflow-y-auto divide-y divide-subtle/50 p-1.5 space-y-1">
          <article
            v-for="r in filteredReports"
            :key="r.id"
            class="group relative rounded-md border transition-all cursor-pointer p-2.5 text-left"
            :class="
              r.id === selectedReportId
                ? 'border-accent bg-accent-soft/30 shadow-xs ring-1 ring-accent'
                : 'border-transparent bg-surface hover:border-subtle hover:bg-surface-muted/60'
            "
            @click="selectReport(r)"
          >
            <!-- Top line: Company Name + Status badge -->
            <div class="flex items-center justify-between gap-1.5 text-xs">
              <span class="truncate font-semibold uppercase tracking-wider text-accent text-[11px]">
                {{ r.company_name || r.company_id }}
              </span>

              <!-- Status Badge -->
              <span
                v-if="normalizeStatus(r.status) === 'complete'"
                class="inline-flex shrink-0 items-center gap-1 rounded bg-success-soft px-1.5 py-0.5 text-[10px] font-medium text-success-ink"
              >
                <CheckCircle2 class="h-2.5 w-2.5" />
                {{ t("reports.status_complete") }}
              </span>
              <span
                v-else-if="normalizeStatus(r.status) === 'running'"
                class="inline-flex shrink-0 items-center gap-1 rounded bg-info-soft px-1.5 py-0.5 text-[10px] font-medium text-info-ink"
              >
                <Loader2 class="h-2.5 w-2.5 animate-spin" />
                {{ t("reports.status_running") }}
              </span>
              <span
                v-else-if="normalizeStatus(r.status) === 'needs_attention'"
                class="inline-flex shrink-0 items-center gap-1 rounded bg-warning-soft px-1.5 py-0.5 text-[10px] font-medium text-warning-ink"
              >
                <AlertCircle class="h-2.5 w-2.5" />
                {{ t("reports.status_needs_attention") }}
              </span>
              <span
                v-else
                class="inline-flex shrink-0 items-center gap-1 rounded bg-danger/10 px-1.5 py-0.5 text-[10px] font-medium text-danger"
              >
                {{ t("reports.status_failed") }}
              </span>
            </div>

            <!-- Second line: Report Title & Date -->
            <div class="mt-1 flex items-baseline justify-between gap-2">
              <h3 class="truncate text-xs font-medium text-ink-primary" :title="r.title || reportKindLabel(r.kind || r.report_type)">
                {{ r.title || reportKindLabel(r.kind || r.report_type) }}
              </h3>
              <span class="shrink-0 text-[10px] text-ink-muted">
                {{ fmtDate(r.created_at) }}
              </span>
            </div>

            <!-- Third line: Language Chips, Quality Lint, Quick Actions -->
            <div class="mt-1.5 flex items-center justify-between gap-2 text-[10px]">
              <div class="flex items-center gap-1">
                <span
                  v-for="lang in Object.keys(r.download_urls || {})"
                  :key="lang"
                  class="rounded bg-surface-muted px-1 py-0.2 font-mono text-[9px] uppercase font-semibold text-ink-secondary border border-subtle"
                >
                  {{ lang }}
                </span>
                <span
                  v-if="r.memo_quality_lint?.overall_score != null"
                  class="inline-flex items-center gap-0.5 rounded bg-surface px-1 py-0.2 text-[9px] font-mono border border-subtle text-accent"
                  :title="`Quality Score: ${r.memo_quality_lint.overall_score}`"
                >
                  <Sparkles class="h-2 w-2" />
                  {{ r.memo_quality_lint.overall_score }}
                </span>
              </div>

              <div class="flex items-center gap-1.5">
                <RouterLink
                  v-if="r.company_id"
                  :to="{ name: 'research', params: { companyId: r.company_id }, query: { tab: 'memo', report: r.id } }"
                  class="text-ink-muted hover:text-ink-primary hover:underline"
                  @click.stop
                >
                  {{ t("reports.open_report") }}
                </RouterLink>

                <a
                  v-if="r.download_urls?.en"
                  :href="withApiToken(r.download_urls.en)"
                  class="inline-flex items-center gap-0.5 rounded border border-subtle px-1 text-[9px] text-ink-muted hover:text-ink-primary hover:bg-surface-muted"
                  :title="t('research.download_en')"
                  @click.stop
                >
                  <Download class="h-2.5 w-2.5" />
                  <span>EN</span>
                </a>

                <a
                  v-if="r.download_urls?.zh"
                  :href="withApiToken(r.download_urls.zh)"
                  class="inline-flex items-center gap-0.5 rounded border border-subtle px-1 text-[9px] text-ink-muted hover:text-ink-primary hover:bg-surface-muted"
                  :title="t('research.download_zh')"
                  @click.stop
                >
                  <Download class="h-2.5 w-2.5" />
                  <span>ZH</span>
                </a>
              </div>
            </div>
          </article>
        </div>
      </aside>

      <!-- Detail Document Viewer Window (Right Pane - Edge-to-Edge) -->
      <section class="flex-1 flex flex-col h-full min-w-0 overflow-hidden bg-surface-muted/20">
        <DocumentViewerWindow
          :title="activeReport?.title || (activeReport ? `${activeReport.company_name || activeReport.company_id} — ${reportKindLabel(activeReport.kind || activeReport.report_type)}` : '')"
          :company-name="activeReport?.company_name || activeReport?.company_id || ''"
          :company-id="activeReport?.company_id || ''"
          :report-id="activeReport?.id || ''"
          :date="fmtDate(activeReport?.created_at)"
          :sources="activeSources"
          :initial-key="route.query.lang || 'EN'"
          @open-fullscreen="openFullscreenDrawer"
        />
      </section>
    </div>

    <!-- Fullscreen Teleported Drawer -->
    <DocumentViewerDrawer
      v-if="drawerState.open"
      :title="drawerState.title"
      :sources="drawerState.sources"
      @close="closeFullscreenDrawer"
    />
  </div>
</template>
