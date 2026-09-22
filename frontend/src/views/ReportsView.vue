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
  FileText,
  Filter,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  SlidersHorizontal,
  ShieldCheck,
  Sparkles,
} from "lucide-vue-next";
import { api, withApiToken } from "../api.js";
import { normalizeReportStatus } from "../formatters.js";
import { useT } from "../i18n.js";
import AiMark from "../components/AiMark.vue";
import DocumentViewerWindow from "../components/DocumentViewerWindow.vue";
import DocumentViewerDrawer from "../components/DocumentViewerDrawer.vue";
import Monogram from "../components/Monogram.vue";
import { useLargeTitle, useMediaQuery } from "../chrome.js";

const t = useT();
const route = useRoute();
const router = useRouter();

// The reports list collapses to a rail, the same move the Research Desk
// directory makes: below `lg` the preview already takes the full width, so
// there is nothing to collapse there.
const REPORTS_COLLAPSED_KEY = "bsh.reportsListCollapsed";
const isSplitWidth = useMediaQuery("(min-width: 1024px)");

function _initialListCollapsed() {
  try {
    return window.localStorage.getItem(REPORTS_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

const listCollapsedPref = ref(_initialListCollapsed());
const listCollapsed = computed(
  () => listCollapsedPref.value && isSplitWidth.value,
);

watch(listCollapsedPref, (collapsed) => {
  try {
    window.localStorage.setItem(REPORTS_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    // ignore — localStorage unavailable
  }
});

function toggleList() {
  listCollapsedPref.value = !listCollapsedPref.value;
}
const pageTitleEl = ref(null);
useLargeTitle(pageTitleEl);

const openReportCustomizer = inject("openReportCustomizer", () => {});

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

const normalizeStatus = normalizeReportStatus;

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

function formatReportCompanyName(r) {
  if (!r) return "";
  if (r.company_name && r.company_name !== "x") {
    return r.company_name;
  }
  if (r.company_id && r.company_id !== "x") {
    return r.company_id;
  }
  return "Investment Report";
}

function reportCompany(r) {
  if (!r) return {};
  const cid = r.company_id || "";
  const match = (workspaceCompanies.value || []).find(
    (c) => c.id === cid || c.ticker?.toLowerCase() === cid.toLowerCase(),
  );
  return {
    ...(match || {}),
    id: r.company_id,
    name: formatReportCompanyName(r),
    ticker: r.ticker || match?.ticker || (cid && cid.length <= 5 && !cid.includes("-") ? cid.toUpperCase() : null),
    logo_url: r.logo_url || match?.logo_url,
    logo_domain: r.logo_domain || match?.logo_domain,
    website: r.website || match?.website,
  };
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
      map.set(r.company_id, formatReportCompanyName(r));
    }
  }
  // A company picked from the sidebar menu may have no reports yet. Listed
  // anyway, or the select would fall back to showing "All companies" over
  // a list that is really filtered to it.
  const picked = selectedCompany.value;
  if (picked && picked !== "all" && !map.has(picked)) {
    map.set(picked, selectedCompanyName.value);
  }
  return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
});

const selectedCompanyName = computed(() => {
  const id = selectedCompany.value;
  if (!id || id === "all") return "";
  const known = (workspaceCompanies.value || []).find((c) => c.id === id);
  const reported = reports.value.find((r) => r.company_id === id);
  return known?.name || (reported ? formatReportCompanyName(reported) : id);
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

// One count beside the title: every report, or how many of them the search
// and filters leave.
const countLabel = computed(() => {
  const shown = filteredReports.value.length;
  const total = stats.value.total;
  return shown === total
    ? t("reports.total_count", { count: total })
    : t("reports.filtered_count", { shown, total });
});

const selectedKindLabel = computed(
  () => kindOptions.value.find((k) => k.id === selectedKind.value)?.label || "",
);

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

// The sidebar's company menu → Reports lands here with `?company=<id>`,
// often while Reports is already open for another company.
watch(
  () => route.query.company,
  (company) => {
    selectedCompany.value = String(company || "all");
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
  <!-- No header row above the panes: the desk's title, search and filters sit
       on the list they filter, so the document runs the window's height. -->
  <div class="flex h-[calc(100vh-52px)] w-full flex-col gap-3 overflow-hidden px-3 pb-3 pt-1 md:px-4 md:pb-4">
    <div v-if="error" class="banner-danger flex shrink-0 items-center gap-3 !text-footnote">
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

    <!-- Master-detail: two floating panes on the canvas, like the Mac Documents desk. -->
    <div class="flex min-h-0 w-full flex-1 gap-3">
      <aside
        class="desk-card flex shrink-0 flex-col overflow-hidden"
        :class="listCollapsed ? 'w-[44px]' : 'w-80 lg:w-[22rem]'"
      >
        <!-- Collapsed: a rail whose only job is to bring the list back. -->
        <button
          v-if="listCollapsed"
          type="button"
          class="focus-ring flex h-full w-full flex-col items-center gap-2 py-3 text-ink-muted transition hover:text-ink-primary"
          :aria-label="t('reports.expand_list')"
          :title="t('reports.expand_list')"
          :aria-expanded="false"
          data-testid="reports-list-expand"
          @click="toggleList"
        >
          <PanelLeftOpen class="h-4 w-4 shrink-0" />
          <span class="text-caption1 font-semibold [writing-mode:vertical-rl]">
            {{ t("reports.total_count", { count: filteredReports.length }) }}
          </span>
        </button>

        <template v-else>
        <div class="flex shrink-0 flex-col gap-2 px-3 pb-2 pt-2.5" data-testid="reports-list-header">
          <div class="flex items-center gap-2">
            <div class="flex min-w-0 flex-1 items-baseline gap-2">
              <h1 ref="pageTitleEl" class="min-w-0 truncate text-headline font-semibold text-ink-primary">
                {{ t("reports.title") }}
              </h1>
              <span class="shrink-0 text-footnote text-ink-muted tabular" data-testid="reports-count">
                {{ countLabel }}
              </span>
            </div>
            <span
              v-if="stats.running > 0"
              class="chip shrink-0 bg-info-soft text-info-ink"
            >
              <Loader2 class="h-3 w-3 animate-spin" />
              {{ stats.running }} {{ t("reports.status_running") }}
            </span>
            <button
              v-if="isSplitWidth"
              type="button"
              class="icon-btn !h-6 !w-6 -mr-1 shrink-0 text-ink-muted"
              :aria-label="t('reports.collapse_list')"
              :title="t('reports.collapse_list')"
              :aria-expanded="true"
              data-testid="reports-list-collapse"
              @click="toggleList"
            >
              <PanelLeftClose class="h-3.5 w-3.5" />
            </button>
          </div>

          <div class="flex items-center gap-1.5">
            <div class="relative min-w-0 flex-1">
              <Search class="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted" />
              <input
                v-model="searchQuery"
                type="text"
                :placeholder="t('reports.search_placeholder')"
                class="news-search-field !py-[5px] !text-footnote"
              />
            </div>
            <button
              type="button"
              class="icon-btn !h-7 !w-7 shrink-0"
              :title="`${t('memo.generate_report')} (⌘N)`"
              :aria-label="t('memo.generate_report')"
              data-testid="reports-generate"
              @click="openReportCustomizer(selectedCompany !== 'all' ? selectedCompany : null)"
            >
              <AiMark class="h-4 w-4 shrink-0" />
            </button>
            <button
              type="button"
              class="icon-btn !h-7 !w-7 shrink-0 text-ink-muted"
              :disabled="loading"
              :title="t('common.refresh')"
              :aria-label="t('common.refresh')"
              data-testid="reports-refresh"
              @click="loadReports"
            >
              <RefreshCw class="h-3.5 w-3.5" :class="{ 'animate-spin': loading }" />
            </button>
          </div>

          <!-- Company names run long, so its filter gets the widest share. -->
          <div
            class="grid gap-1.5"
            :class="kindOptions.length > 1 ? 'grid-cols-[1.35fr_1fr_1.1fr]' : 'grid-cols-[1.35fr_1.1fr]'"
          >
            <select
              v-model="selectedCompany"
              class="field field-sm reports-filter w-full min-w-0"
              :title="selectedCompanyName || t('reports.filter_company')"
            >
              <option value="all">{{ t("reports.filter_company") }}</option>
              <option v-for="c in companyOptions" :key="c.id" :value="c.id">
                {{ c.name }}
              </option>
            </select>

            <select
              v-if="kindOptions.length > 1"
              v-model="selectedKind"
              class="field field-sm reports-filter w-full min-w-0"
              :title="selectedKindLabel || t('reports.filter_kind')"
            >
              <option value="all">{{ t("reports.filter_kind") }}</option>
              <option v-for="k in kindOptions" :key="k.id" :value="k.id">
                {{ k.label }}
              </option>
            </select>

            <select v-model="selectedStatus" class="field field-sm reports-filter w-full min-w-0">
              <option value="all">{{ t("reports.filter_status") }}</option>
              <option value="complete">{{ t("reports.status_complete") }}</option>
              <option value="running">{{ t("reports.status_running") }}</option>
              <option value="needs_attention">{{ t("reports.status_needs_attention") }}</option>
              <option value="failed">{{ t("reports.status_failed") }}</option>
            </select>
          </div>
        </div>

        <div
          v-if="loading"
          class="flex flex-1 flex-col items-center justify-center p-6 text-center text-footnote text-ink-muted"
        >
          <Loader2 class="mb-2 h-5 w-5 animate-spin text-accent" />
          <p>{{ t("documents.viewer_loading") }}</p>
        </div>

        <div
          v-else-if="!filteredReports.length"
          class="flex flex-1 flex-col items-center justify-center p-6 text-center text-ink-muted"
        >
          <span class="mb-2 grid h-11 w-11 place-items-center rounded-[12px] bg-ink-primary/[0.05]">
            <FileText class="h-5 w-5 text-ink-subtle" />
          </span>
          <div class="text-callout font-semibold text-ink-primary">
            {{ selectedCompanyName ? t("reports.empty_company_title", { name: selectedCompanyName }) : t("reports.empty_title") }}
          </div>
          <p class="mt-1 max-w-xs text-footnote text-ink-muted">{{ t("reports.empty_desc") }}</p>
          <button
            type="button"
            class="btn-filled btn-sm mt-3 inline-flex items-center gap-1.5 focus-ring"
            @click="openReportCustomizer(selectedCompany !== 'all' ? selectedCompany : null)"
          >
            <AiMark class="h-3.5 w-3.5 shrink-0" />
            <span>{{ t("memo.generate_report") }}</span>
          </button>
        </div>

        <div v-else class="flex-1 space-y-0.5 overflow-y-auto px-1.5 pb-1.5">
          <article
            v-for="r in filteredReports"
            :key="r.id"
            class="doc-row"
            :data-selected="r.id === selectedReportId ? 'true' : 'false'"
            @click="selectReport(r)"
          >
            <Monogram
              :company="reportCompany(r)"
              :size="34"
              tinted
              class="mt-0.5"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-baseline justify-between gap-2">
                <span class="truncate text-callout font-semibold text-ink-primary">
                  {{ formatReportCompanyName(r) }}
                </span>
                <span class="shrink-0 text-caption1 text-ink-muted tabular">
                  {{ fmtDate(r.created_at) }}
                </span>
              </div>

              <div class="mt-0.5 flex items-center justify-between gap-2">
                <h3 class="truncate text-footnote text-ink-secondary" :title="r.title || reportKindLabel(r.kind || r.report_type)">
                  {{ r.title || reportKindLabel(r.kind || r.report_type) }}
                </h3>
                <span
                  v-if="normalizeStatus(r.status) === 'complete'"
                  class="chip shrink-0 bg-success-soft text-success-ink"
                >
                  <CheckCircle2 class="h-3 w-3" />
                  {{ t("reports.status_complete") }}
                </span>
                <span
                  v-else-if="normalizeStatus(r.status) === 'running'"
                  class="chip shrink-0 bg-info-soft text-info-ink"
                >
                  <Loader2 class="h-3 w-3 animate-spin" />
                  {{ t("reports.status_running") }}
                </span>
                <span
                  v-else-if="normalizeStatus(r.status) === 'needs_attention'"
                  class="chip shrink-0 bg-warning-soft text-warning-ink"
                >
                  <AlertCircle class="h-3 w-3" />
                  {{ t("reports.status_needs_attention") }}
                </span>
                <span
                  v-else
                  class="chip shrink-0 bg-danger-soft text-danger-ink"
                >
                  {{ t("reports.status_failed") }}
                </span>
              </div>

              <div class="mt-1.5 flex items-center justify-between gap-2 text-caption1">
                <div class="flex items-center gap-1">
                  <span
                    v-for="lang in Object.keys(r.download_urls || {})"
                    :key="lang"
                    class="rounded-[5px] bg-ink-primary/[0.06] px-1.5 py-px text-caption2 font-semibold uppercase text-ink-secondary"
                  >
                    {{ lang }}
                  </span>
                  <span
                    v-if="r.memo_quality_lint?.overall_score != null"
                    class="inline-flex items-center gap-0.5 rounded-[5px] bg-accent/10 px-1.5 py-px text-caption2 font-semibold text-accent-ink tabular"
                    :title="`Quality Score: ${r.memo_quality_lint.overall_score}`"
                  >
                    <Sparkles class="h-2.5 w-2.5" />
                    {{ r.memo_quality_lint.overall_score }}
                  </span>
                  <span
                    v-if="r.memo_fact_check?.coverage_pct != null"
                    class="inline-flex items-center gap-0.5 rounded-[5px] px-1.5 py-px text-caption2 font-semibold tabular"
                    :class="r.memo_fact_check.unsupported ? 'bg-amber-500/10 text-amber-700' : 'bg-emerald-500/10 text-emerald-700'"
                    :title="t('research.fact_check_traced', { pct: r.memo_fact_check.coverage_pct })"
                    data-testid="fact-check-chip"
                  >
                    <ShieldCheck class="h-2.5 w-2.5" />
                    {{ r.memo_fact_check.coverage_pct }}%
                  </span>
                </div>

                <div class="flex items-center gap-2">
                  <RouterLink
                    v-if="r.company_id"
                    :to="{ name: 'research', params: { companyId: r.company_id }, query: { tab: 'memo', report: r.id } }"
                    class="font-medium text-accent-ink hover:underline"
                    @click.stop
                  >
                    {{ t("reports.open_report") }}
                  </RouterLink>

                  <a
                    v-if="r.download_urls?.en"
                    :href="withApiToken(r.download_urls.en)"
                    class="inline-flex items-center gap-0.5 rounded-[5px] px-1 text-ink-muted hover:bg-ink-primary/[0.06] hover:text-ink-primary"
                    :title="t('research.download_en')"
                    @click.stop
                  >
                    <Download class="h-3 w-3" />
                    <span>EN</span>
                  </a>

                  <a
                    v-if="r.download_urls?.zh"
                    :href="withApiToken(r.download_urls.zh)"
                    class="inline-flex items-center gap-0.5 rounded-[5px] px-1 text-ink-muted hover:bg-ink-primary/[0.06] hover:text-ink-primary"
                    :title="t('research.download_zh')"
                    @click.stop
                  >
                    <Download class="h-3 w-3" />
                    <span>ZH</span>
                  </a>
                </div>
              </div>
            </div>
          </article>
        </div>
        </template>
      </aside>

      <section class="desk-card flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <DocumentViewerWindow
          :title="activeReport?.title || (activeReport ? `${formatReportCompanyName(activeReport)} — ${reportKindLabel(activeReport.kind || activeReport.report_type)}` : '')"
          :company-name="formatReportCompanyName(activeReport)"
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
