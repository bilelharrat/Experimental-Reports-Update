<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowLeft,
  Download,
  Eye,
  ExternalLink,
  FileText,
  Loader2,
  Send,
  Sparkles,
} from "lucide-vue-next";
import { api, withApiToken } from "../api.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import CompanyLibrary from "../components/CompanyLibrary.vue";
import ResearchUploads from "../components/ResearchUploads.vue";
import CompanyDetail from "../components/CompanyDetail.vue";
import CompanyConsole from "../components/CompanyConsole.vue";
import FilePreviewModal from "../components/FilePreviewModal.vue";
import MemoAnalysisDashboard from "../components/MemoAnalysisDashboard.vue";

const tr = useT();

// Backend returns canonical option strings (e.g. "Investment Memo (Late-Stage)",
// "Internal"). Map them to localized display labels here; unknown values fall
// through to the raw string so new server-side options keep working.
const REPORT_TYPE_ZH = {
  "Investment Memo (Late-Stage)": "投资备忘录（Late-Stage / Pre-IPO）",
};
const AUDIENCE_ZH = {
  Internal: "内部",
  External: "外部",
};
const MEMO_REPORT_TYPE = "Investment Memo (Late-Stage)";
function reportTypeLabel(val) {
  if (appLanguage.value === "zh") return REPORT_TYPE_ZH[val] || val;
  return val;
}
function audienceLabel(val) {
  if (appLanguage.value === "zh") return AUDIENCE_ZH[val] || val;
  return val;
}

const props = defineProps({ companyId: { type: String, required: true } });
const emit = defineEmits(["reports-changed"]);

const route = useRoute();
const router = useRouter();

const company = ref(null);
const companyError = ref(null);
const options = ref({ report_types: [], audiences: [], languages: [] });

const isPublicCompany = computed(() => {
  const c = company.value;
  if (!c) return false;
  return String(c.company_type || "").trim().toLowerCase() === "public";
});
const canShowMemoStudio = computed(() =>
  Boolean(company.value && !isPublicCompany.value),
);

// Default to the late-stage investment memo — the only fully-wired
// pipeline. Other types still route through the legacy stub generator.
const reportType = ref(MEMO_REPORT_TYPE);
const audience = ref("Internal");

const activeReport = ref(null);
const resuming = ref(false);
const startingFresh = ref(false);
// The Generate button is "generating" only when a report is actively
// in-flight. Terminal failure states (failed_scope_check,
// failed_during_analysis, failed_orphaned) leave the button clickable
// so the user can kick off a fresh run.
const generating = computed(() => {
  if (startingFresh.value) return true;
  const r = activeReport.value;
  if (!r) return false;
  const status = String(r.status || "");
  const terminal =
    status === "complete" ||
    status === "complete_with_warnings" ||
    status.startsWith("failed");
  return !terminal;
});

// Memo report — language toggle for the preview pane.
const previewLanguage = ref("en");
const isMemo = computed(
  () => activeReport.value?.kind === "investment_memo_latestage",
);
const memoPreview = computed(() => {
  const r = activeReport.value;
  if (!r) return "";
  if (previewLanguage.value === "zh") return r.content_zh || r.content || "";
  return r.content_en || r.content || "";
});
const reportFailureDetail = computed(() => {
  const r = activeReport.value;
  if (!r) return "";
  return r.failure_detail || r.error || r.stage || "";
});
const reportIsFailed = computed(() =>
  String(activeReport.value?.status || "").startsWith("failed"),
);
const canResumeMemo = computed(() =>
  Boolean(
    isMemo.value &&
      reportIsFailed.value &&
      activeReport.value?.resume_available,
  ),
);
const reportFailureTitle = computed(() => {
  const r = activeReport.value;
  if (!r) return "";
  if (
    r.failure_phase === "renderer_contract" ||
    String(r.stage || "").toLowerCase().includes("renderer")
  ) {
    return tr("research.failed_run_renderer");
  }
  if (r.failure_phase === "internal_diligence_memo") {
    return tr("research.failed_run_internal_memo");
  }
  if (r.failure_phase === "chinese_parity_gate") {
    return tr("research.failed_run_chinese_parity");
  }
  if (
    r.failure_phase === "quality_gate" ||
    String(r.status || "") === "failed_quality_gate" ||
    String(r.stage || "").toLowerCase().includes("quality")
  ) {
    return tr("research.failed_run_quality_gate");
  }
  return tr("research.failed_run_generic");
});
const reportHeadline = computed(() => {
  const r = activeReport.value;
  if (!r) return "";
  if (reportIsFailed.value) return r.stage || reportFailureTitle.value;
  return r.stage || r.status || "";
});
const analysisArtifacts = computed(() => {
  const artifacts = activeReport.value?.analysis_artifacts;
  return Array.isArray(artifacts) ? artifacts : [];
});
const memoArtifactsVisible = computed(() => {
  const r = activeReport.value;
  if (!isMemo.value || !r) return false;
  const downloadUrls = r.download_urls || {};
  const previewUrls = r.preview_urls || {};
  return Boolean(
    Object.keys(downloadUrls).length ||
      Object.keys(previewUrls).length ||
      analysisArtifacts.value.length ||
      r.content_en ||
      r.content_zh,
  );
});
const rendererContractErrors = computed(() => {
  const errors = activeReport.value?.renderer_contract?.errors;
  return Array.isArray(errors) ? errors : [];
});
const rendererContractFiles = computed(() => {
  const files = activeReport.value?.renderer_contract?.expected_files;
  return Array.isArray(files) ? files : [];
});

// PDF preview popup (reuses the generic FilePreviewModal). `previewFile`
// non-null = modal open; we hand the modal explicit tokened URLs since
// it fetches the preview blob with a plain fetch (no auth header).
const previewFile = ref(null);
const previewPdfUrl = ref(null);
const previewDocxUrl = ref(null);
function openMemoPreview(kind) {
  const r = activeReport.value;
  const purl = r?.preview_urls?.[kind];
  if (!purl) return;
  previewPdfUrl.value = withApiToken(purl);
  previewDocxUrl.value = r?.download_urls?.[kind]
    ? withApiToken(r.download_urls[kind])
    : null;
  const name = r?.company_name || company.value?.name || "Memo";
  const isInternal = kind === "internal";
  previewFile.value = {
    id: `memo-${r.id}-${kind}`,
    kind: "pdf",
    label: isInternal
      ? `${name} — Internal Diligence Memo`
      : `${name} — ${kind === "zh" ? "投资备忘录" : "Investment Memo"}`,
    filename: isInternal
      ? `${name} - Internal Diligence Memo.pdf`
      : `${name} - Investment Memo (${kind.toUpperCase()}).pdf`,
    language: kind,
  };
}
function closeMemoPreview() {
  previewFile.value = null;
  previewPdfUrl.value = null;
  previewDocxUrl.value = null;
}

const threads = ref([]);
const newQuestion = ref("");
const newAnswer = ref("");
const submittingThread = ref(false);

const libraryRefresh = ref(0);

// Three-tab shell: overview (default), documents, console. Tab selection
// is per-mount — switching companies resets to overview. Persisted in the
// route query so a deep-linked URL preserves the tab.
const activeTab = ref(route.query.tab || "overview");
function switchTab(name) {
  const nextTab =
    name === "analysis" && company.value && !canShowMemoStudio.value
      ? "overview"
      : name;
  activeTab.value = nextTab;
  router.replace({
    name: "research",
    params: { companyId: props.companyId },
    query: { ...route.query, tab: nextTab === "overview" ? undefined : nextTab },
  });
}
watch(() => route.query.tab, (v) => {
  activeTab.value = v || "overview";
});
function normalizeActiveTabForCompany() {
  if (activeTab.value === "analysis" && company.value && !canShowMemoStudio.value) {
    switchTab("overview");
  }
}
watch(
  [activeTab, canShowMemoStudio, () => company.value?.id],
  normalizeActiveTabForCompany,
);

let pollId = null;

// Map the HTTP status onto a localized title + body. 404 keeps the
// existing "Company not found" copy; 401/403 explain the session
// rather than blaming the company id; anything else surfaces a
// generic error with the underlying status so we don't bury an
// 5xx as "company not found".
const companyErrorTitle = computed(() => {
  const s = companyError.value?.status;
  if (s === 401 || s === 403) return tr("research.session_expired");
  if (s === 404) return tr("research.company_not_found");
  return tr("research.company_load_failed");
});
const companyErrorBody = computed(() => {
  const s = companyError.value?.status;
  if (s === 401 || s === 403) return tr("research.session_expired_body");
  if (s === 404) return tr("research.company_not_found_body", { id: props.companyId });
  return tr("research.company_load_failed_body", { id: props.companyId });
});

async function loadCompany() {
  companyError.value = null;
  try {
    company.value = await api.getCompany(props.companyId);
  } catch (e) {
    // Keep the HTTP status on the error object so the template can
    // tell "company genuinely missing" from "your session expired" /
    // "something else went wrong". Distinguishing these is the
    // difference between "go add this company" and "sign in and
    // try again".
    companyError.value = {
      message: e?.message || String(e),
      status: e?.status ?? null,
    };
  }
}

async function loadOptions() {
  try {
    options.value = await api.options();
    if (!options.value.report_types.includes(reportType.value)) {
      reportType.value = options.value.report_types[0] || reportType.value;
    }
    if (!options.value.audiences.includes(audience.value)) {
      audience.value = options.value.audiences[0] || audience.value;
    }
  } catch (e) {
    // non-fatal — keep defaults.
  }
}

async function loadThreads() {
  try {
    threads.value = await api.listThreads(props.companyId);
  } catch (e) {
    threads.value = [];
  }
}

async function pollReport() {
  if (!activeReport.value) return;
  try {
    const r = await api.getReport(activeReport.value.id);
    activeReport.value = r;
    const status = String(r.status || "");
    if (
      status === "complete" ||
      status === "complete_with_warnings" ||
      status.startsWith("failed")
    ) {
      stopPolling();
      if (status === "complete" || status === "complete_with_warnings") {
        emit("reports-changed");
        libraryRefresh.value += 1;
      }
    }
  } catch (e) {
    stopPolling();
  }
}

async function openReportFromLibrary(r) {
  router.replace({
    name: "research",
    params: { companyId: props.companyId },
    query: { report: r.id },
  });
}

function startPolling() {
  stopPolling();
  pollId = setInterval(pollReport, 1000);
}
function stopPolling() {
  if (pollId) clearInterval(pollId);
  pollId = null;
}

async function generate(analysisSessionId = null, options = {}) {
  const memoAnalysisSessionId =
    typeof analysisSessionId === "string" ? analysisSessionId : null;
  const forceFresh = Boolean(options?.forceFresh);
  if (canResumeMemo.value && !forceFresh) {
    await resumeReport();
    return;
  }
  startingFresh.value = true;
  try {
    const r = await api.generateReport({
      company_id: props.companyId,
      report_type: reportType.value,
      audience: audience.value,
      // Language is fixed at the server: investment-memo runs always
      // produce both EN + ZH; legacy report types default to en.
      language: "en",
      analysis_session_id: memoAnalysisSessionId,
    });
    activeReport.value = r;
    // Hop the URL to the new report so a refresh lands on the fresh
    // run, not whatever the user was viewing before (e.g. a stale
    // failed_* orphan).
    router.replace({
      name: "research",
      params: { companyId: props.companyId },
      query: { report: r.id },
    });
    emit("reports-changed");
    startPolling();
  } catch (e) {
    companyError.value = e.message;
  } finally {
    startingFresh.value = false;
  }
}

async function resumeReport() {
  const reportId = activeReport.value?.id;
  if (!reportId || !canResumeMemo.value) return;
  resuming.value = true;
  try {
    const r = await api.resumeReport(reportId);
    activeReport.value = r;
    emit("reports-changed");
    startPolling();
  } catch (e) {
    companyError.value = e.message;
  } finally {
    resuming.value = false;
  }
}

async function submitThread() {
  if (!newQuestion.value.trim()) return;
  submittingThread.value = true;
  try {
    await api.addThread(props.companyId, {
      question: newQuestion.value.trim(),
      answer: newAnswer.value.trim(),
    });
    newQuestion.value = "";
    newAnswer.value = "";
    await loadThreads();
  } finally {
    submittingThread.value = false;
  }
}

async function loadFromQuery() {
  const reportId = route.query.report;
  if (reportId) {
    try {
      activeReport.value = await api.getReport(reportId);
      if (activeReport.value.status !== "complete") startPolling();
    } catch (e) {
      activeReport.value = null;
    }
  } else {
    activeReport.value = null;
    stopPolling();
  }
}

watch(
  () => props.companyId,
  async () => {
    activeReport.value = null;
    stopPolling();
    await Promise.all([loadCompany(), loadThreads()]);
    await loadFromQuery();
  },
);

watch(() => route.query.report, loadFromQuery);

onMounted(async () => {
  await Promise.all([loadOptions(), loadCompany(), loadThreads()]);
  await loadFromQuery();
});

onUnmounted(stopPolling);
</script>

<template>
  <div class="w-full px-8 py-10 space-y-8">
    <div>
      <button
        @click="router.push({ name: 'home' })"
        class="text-sm text-ink-muted hover:text-ink-primary inline-flex items-center gap-1 focus-ring rounded"
      >
        <ArrowLeft class="h-4 w-4" /> {{ tr("research.back_to_search") }}
      </button>
    </div>

    <CompanyDetail
      v-if="company"
      :company="company"
      @refreshed="(c) => (company = c)"
    />

    <div
      v-else-if="companyError"
      class="rounded-card border border-subtle bg-surface p-6 text-center"
    >
      <div class="font-display text-lg text-ink-primary">
        {{ companyErrorTitle }}
      </div>
      <p class="mt-1 text-sm text-ink-muted">
        {{ companyErrorBody }}
      </p>
      <p v-if="companyError.status && companyError.status !== 404" class="mt-1 text-[11px] text-ink-muted font-mono">
        HTTP {{ companyError.status }} · {{ companyError.message }}
      </p>
      <button
        @click="router.push({ name: 'home' })"
        class="mt-3 text-sm text-accent hover:text-accent-hover focus-ring rounded"
      >
        {{ tr("research.back_to_search") }}
      </button>
    </div>
    <div v-else class="text-sm text-ink-muted">{{ tr("common.loading") }}</div>

    <!-- Three-tab shell — Overview / Documents / Console. -->
    <div v-if="company" class="flex items-center gap-1 border-b border-subtle">
      <button
        @click="switchTab('overview')"
        :class="[
          'px-4 py-2 text-sm font-medium focus-ring rounded-t-lg',
          activeTab === 'overview'
            ? 'text-ink-primary border-b-2 border-accent -mb-px'
            : 'text-ink-muted hover:text-ink-primary',
        ]"
      >
        {{ tr("research.tab_overview") }}
      </button>
      <button
        @click="switchTab('documents')"
        :class="[
          'px-4 py-2 text-sm font-medium focus-ring rounded-t-lg',
          activeTab === 'documents'
            ? 'text-ink-primary border-b-2 border-accent -mb-px'
            : 'text-ink-muted hover:text-ink-primary',
        ]"
      >
        {{ tr("research.tab_documents") }}
      </button>
      <button
        v-if="canShowMemoStudio"
        @click="switchTab('analysis')"
        :class="[
          'px-4 py-2 text-sm font-medium focus-ring rounded-t-lg',
          activeTab === 'analysis'
            ? 'text-ink-primary border-b-2 border-accent -mb-px'
            : 'text-ink-muted hover:text-ink-primary',
        ]"
      >
        {{ tr("research.tab_analysis") }}
      </button>
      <button
        @click="switchTab('console')"
        :class="[
          'px-4 py-2 text-sm font-medium focus-ring rounded-t-lg',
          activeTab === 'console'
            ? 'text-ink-primary border-b-2 border-accent -mb-px'
            : 'text-ink-muted hover:text-ink-primary',
        ]"
      >
        {{ tr("research.tab_console") }}
      </button>
    </div>

    <CompanyConsole
      v-if="company && activeTab === 'console'"
      :company-id="companyId"
    />

    <MemoAnalysisDashboard
      v-if="canShowMemoStudio && activeTab === 'analysis'"
      :company-id="companyId"
      @generate-memo="generate"
    />

    <section
      v-if="company && activeTab === 'overview'"
      class="bg-surface border border-subtle rounded-card shadow-card p-6"
    >
      <h2 class="font-display text-lg font-semibold text-ink-primary mb-4">
        {{ tr("research.generate_report") }}
      </h2>
      <div class="grid sm:grid-cols-2 gap-4">
        <label class="block">
          <div class="text-xs font-medium text-ink-muted uppercase tracking-wide mb-1.5">
            {{ tr("research.label_report_type") }}
          </div>
          <select
            v-model="reportType"
            class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary focus-ring"
          >
            <option v-for="t in options.report_types" :key="t" :value="t">
              {{ reportTypeLabel(t) }}
            </option>
          </select>
        </label>
        <label class="block">
          <div class="text-xs font-medium text-ink-muted uppercase tracking-wide mb-1.5">
            {{ tr("research.label_audience") }}
          </div>
          <select
            v-model="audience"
            class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary focus-ring"
          >
            <option v-for="a in options.audiences" :key="a" :value="a">
              {{ audienceLabel(a) }}
            </option>
          </select>
        </label>
      </div>
      <div class="mt-5 flex items-center gap-3">
        <button
          @click="generate"
          :disabled="generating || resuming"
          class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-60 disabled:cursor-not-allowed focus-ring"
        >
          <Loader2 v-if="generating || resuming" class="h-4 w-4 animate-spin" />
          <Sparkles v-else class="h-4 w-4" />
          <span>
            {{
              canResumeMemo
                ? resuming
                  ? tr("research.resuming_memo")
                  : tr("research.resume_memo")
                : generating
                  ? tr("research.generating")
                  : tr("research.generate_button")
            }}
          </span>
        </button>
        <button
          v-if="canResumeMemo"
          type="button"
          @click="generate(null, { forceFresh: true })"
          :disabled="generating || resuming"
          class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 disabled:cursor-not-allowed focus-ring"
        >
          <Sparkles class="h-4 w-4" />
          <span>{{ tr("research.redo_memo") }}</span>
        </button>
        <span v-if="generating" class="text-xs text-ink-muted">
          {{ tr("research.generating_hint") }}
        </span>
        <span
          v-else-if="canResumeMemo"
          class="text-xs text-ink-muted"
        >
          {{ tr("research.resume_or_start_fresh_hint") }}
        </span>
      </div>
    </section>

    <section
      v-if="activeReport && activeTab === 'overview'"
      class="bg-surface border border-subtle rounded-card shadow-card p-6"
    >
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div class="text-xs uppercase tracking-wider text-ink-muted">
            {{ reportTypeLabel(activeReport.report_type) }} ·
            {{ audienceLabel(activeReport.audience) }}
            · {{ (activeReport.language || "en").toUpperCase() }}
          </div>
          <div class="font-display text-lg font-semibold text-ink-primary">
            {{ reportHeadline }}
          </div>
        </div>
        <span
          v-if="activeReport.status === 'complete'"
          class="text-xs px-2 py-1 rounded bg-success-soft text-success-ink"
          >{{ tr("research.status_complete") }}</span
        >
        <span
          v-else-if="reportIsFailed"
          class="text-xs px-2 py-1 rounded bg-danger/10 text-danger"
          >{{ tr("research.status_failed") }}</span
        >
        <span
          v-else
          class="text-xs px-2 py-1 rounded bg-warning-soft text-warning-ink inline-flex items-center gap-1"
        >
          <Loader2 class="h-3 w-3 animate-spin" />
          {{ activeReport.progress }}%
        </span>
      </div>

      <div class="mt-4 h-2 w-full rounded-full bg-surface-muted overflow-hidden">
        <div
          class="h-full bg-accent transition-all"
          :style="{ width: (activeReport.progress || 0) + '%' }"
        ></div>
      </div>

      <div
        v-if="
          isMemo &&
          activeReport.scope_check &&
          activeReport.scope_check.outcome === 'warn'
        "
        class="mt-4 rounded-lg border border-warning bg-warning-soft p-4 text-sm text-warning-ink"
      >
        <div class="font-semibold mb-1">
          {{
            tr("research.scope_check_warning", {
              classification: activeReport.scope_check.classification,
            })
          }}
        </div>
        <p>{{ activeReport.scope_check.reason }}</p>
      </div>

      <ul
        v-if="activeReport.stages && activeReport.stages.length"
        class="mt-4 space-y-1 text-sm"
      >
        <li
          v-for="(s, i) in activeReport.stages"
          :key="i"
          class="flex items-center gap-2 text-ink-secondary"
        >
          <span class="h-1.5 w-1.5 rounded-full bg-accent"></span>
          <span>{{ s.label }}</span>
          <span class="text-ink-muted">— {{ s.progress }}%</span>
        </li>
      </ul>

      <!-- Memo-specific affordances: downloads, partial analysis artifacts,
           and bilingual preview. Shown for complete runs and for failed
           runs when any generated output exists for QA. -->
      <div
        v-if="memoArtifactsVisible"
        class="mt-6 space-y-4"
      >
        <div
          v-if="reportIsFailed"
          class="rounded-lg border border-warning/40 bg-warning-soft/40 px-3 py-2 text-xs text-warning-ink"
        >
          {{ tr("research.failed_artifacts_available") }}
        </div>
        <div
          v-if="analysisArtifacts.length"
          class="border-t border-subtle pt-4"
        >
          <div class="flex items-center gap-2 text-sm font-semibold text-ink-primary">
            <FileText class="h-4 w-4 text-accent" />
            <span>{{ tr("research.partial_analysis_artifacts") }}</span>
          </div>
          <p class="mt-1 text-xs text-ink-muted">
            {{ tr("research.partial_analysis_artifacts_body") }}
          </p>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <a
              v-for="artifact in analysisArtifacts"
              :key="artifact.filename || artifact.label"
              :href="withApiToken(artifact.download_url || '#')"
              class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
            >
              <FileText class="h-4 w-4" />
              <span>{{ artifact.label || artifact.filename }}</span>
              <Download class="h-3.5 w-3.5 text-ink-muted" />
            </a>
          </div>
        </div>
        <!-- Download + preview row: both .docx files (always available
             once complete) plus a PDF preview when one was rendered. -->
        <div class="flex flex-wrap items-center gap-3">
          <a
            v-if="activeReport.download_urls?.en"
            :href="withApiToken(activeReport.download_urls.en)"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          >
            <FileText class="h-4 w-4" />
            <span>{{ tr("research.download_en") }}</span>
            <Download class="h-3.5 w-3.5 text-ink-muted" />
          </a>
          <button
            v-if="activeReport.preview_urls?.en"
            type="button"
            @click="openMemoPreview('en')"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          >
            <Eye class="h-4 w-4" />
            <span>{{ tr("research.preview_pdf_en") }}</span>
          </button>
          <a
            v-if="activeReport.download_urls?.zh"
            :href="withApiToken(activeReport.download_urls.zh)"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          >
            <FileText class="h-4 w-4" />
            <span>{{ tr("research.download_zh") }}</span>
            <Download class="h-3.5 w-3.5 text-ink-muted" />
          </a>
          <button
            v-if="activeReport.preview_urls?.zh"
            type="button"
            @click="openMemoPreview('zh')"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          >
            <Eye class="h-4 w-4" />
            <span>{{ tr("research.preview_pdf_zh") }}</span>
          </button>
          <a
            v-if="activeReport.download_urls?.internal"
            :href="withApiToken(activeReport.download_urls.internal)"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          >
            <FileText class="h-4 w-4" />
            <span>{{ tr("research.download_internal") }}</span>
            <Download class="h-3.5 w-3.5 text-ink-muted" />
          </a>
          <button
            v-if="activeReport.preview_urls?.internal"
            type="button"
            @click="openMemoPreview('internal')"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          >
            <Eye class="h-4 w-4" />
            <span>{{ tr("research.preview_pdf_internal") }}</span>
          </button>
          <a
            v-if="activeReport.run_dir"
            :href="`file://${activeReport.run_dir}`"
            class="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink-primary focus-ring rounded"
            :title="activeReport.run_dir"
          >
            <ExternalLink class="h-3 w-3" />
            <span>{{ tr("research.run_folder") }}</span>
          </a>
        </div>

        <!-- Language toggle for the preview body. -->
        <div
          v-if="activeReport.content_en || activeReport.content_zh"
          class="flex items-center gap-2 text-xs"
        >
          <span class="text-ink-muted uppercase tracking-wide">{{ tr("research.preview_label") }}</span>
          <button
            type="button"
            @click="previewLanguage = 'en'"
            :class="[
              'px-2 py-1 rounded',
              previewLanguage === 'en'
                ? 'bg-accent text-white'
                : 'bg-surface-muted text-ink-secondary hover:bg-surface',
            ]"
          >
            {{ tr("research.preview_en") }}
          </button>
          <button
            type="button"
            @click="previewLanguage = 'zh'"
            :class="[
              'px-2 py-1 rounded',
              previewLanguage === 'zh'
                ? 'bg-accent text-white'
                : 'bg-surface-muted text-ink-secondary hover:bg-surface',
            ]"
          >
            {{ tr("research.preview_zh") }}
          </button>
        </div>

        <pre
          v-if="memoPreview"
          class="whitespace-pre-wrap font-body text-sm leading-relaxed text-ink-primary bg-surface-muted rounded-lg p-4 border border-subtle"
          >{{ memoPreview }}</pre
        >
      </div>

      <!-- Non-memo reports: simple preview block (legacy). -->
      <pre
        v-else-if="activeReport.status === 'complete' && activeReport.content"
        class="mt-6 whitespace-pre-wrap font-body text-sm leading-relaxed text-ink-primary bg-surface-muted rounded-lg p-4 border border-subtle"
        >{{ activeReport.content }}</pre
      >

      <!-- Memo scope-fail: show the reason and the run folder for browsing. -->
      <!-- Generic failure banner for any failed_* memo run. -->
      <div
        v-if="
          isMemo &&
          String(activeReport.status || '').startsWith('failed') &&
          activeReport.status !== 'failed_scope_check'
        "
        class="mt-6 rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm text-ink-primary"
      >
        <div class="font-semibold text-danger mb-1">
          {{ reportFailureTitle }}
        </div>
        <p v-if="activeReport.stage" class="text-ink-secondary">
          {{ activeReport.stage }}
        </p>
        <p
          v-if="reportFailureDetail && reportFailureDetail !== activeReport.stage"
          class="mt-1 text-ink-secondary"
        >
          {{ reportFailureDetail }}
        </p>
        <div v-if="rendererContractErrors.length" class="mt-3">
          <div class="text-xs font-semibold uppercase tracking-wide text-danger">
            {{ tr("research.renderer_contract_checks") }}
          </div>
          <ul class="mt-1 space-y-1 text-xs text-ink-secondary">
            <li v-for="err in rendererContractErrors" :key="err">
              {{ err }}
            </li>
          </ul>
        </div>
        <div v-if="rendererContractFiles.length" class="mt-3">
          <div class="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            {{ tr("research.expected_files") }}
          </div>
          <ul class="mt-1 space-y-1 text-xs text-ink-muted font-mono">
            <li v-for="file in rendererContractFiles" :key="file.label">
              {{ file.label }}:
              {{
                file.exists
                  ? tr("research.expected_file_found")
                  : tr("research.expected_file_missing")
              }}
              <span v-if="file.path">· {{ file.path }}</span>
            </li>
          </ul>
        </div>
        <p v-if="activeReport.run_dir" class="mt-2 text-xs text-ink-muted">
          {{ tr("research.run_folder_preserved_prefix") }}
          <span class="font-mono">{{ activeReport.run_dir }}</span>
        </p>
        <button
          v-if="canResumeMemo"
          type="button"
          @click="resumeReport"
          :disabled="resuming || generating"
          class="mt-3 inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 disabled:cursor-not-allowed focus-ring"
        >
          <Loader2 v-if="resuming" class="h-4 w-4 animate-spin" />
          <Sparkles v-else class="h-4 w-4" />
          <span>{{ resuming ? tr("research.resuming_memo") : tr("research.resume_memo") }}</span>
        </button>
        <p class="mt-2 text-xs text-ink-muted">
          {{
            canResumeMemo
              ? tr("research.resume_or_start_fresh_hint")
              : tr("research.start_fresh_hint")
          }}
        </p>
      </div>

      <div
        v-if="isMemo && activeReport.status === 'failed_scope_check' && activeReport.scope_check"
        class="mt-6 rounded-lg border border-warning bg-warning-soft p-4 text-sm text-warning-ink"
      >
        <div class="font-semibold mb-1">
          {{
            tr("research.scope_check_failed", {
              classification: activeReport.scope_check.classification,
            })
          }}
        </div>
        <p>{{ activeReport.scope_check.reason }}</p>
        <p v-if="activeReport.run_dir" class="mt-2 text-xs text-ink-muted">
          {{ tr("research.run_folder_preserved_prefix") }}
          <span class="font-mono">{{ activeReport.run_dir }}</span>
        </p>
      </div>
    </section>

    <ResearchUploads
      v-if="company && activeTab === 'documents'"
      :company-id="companyId"
    />

    <CompanyLibrary
      v-if="company && activeTab === 'documents'"
      :company-id="companyId"
      :refresh-key="libraryRefresh"
      @open-report="openReportFromLibrary"
    />

    <section
      v-if="company && activeTab === 'overview'"
      class="bg-surface border border-subtle rounded-card shadow-card p-6"
    >
      <h2 class="font-display text-lg font-semibold text-ink-primary mb-1">
        {{ tr("research.knowledge_base") }}
      </h2>
      <p class="text-sm text-ink-muted mb-4">
        {{ tr("research.knowledge_base_subtitle") }}
      </p>

      <form @submit.prevent="submitThread" class="space-y-2 mb-5">
        <input
          v-model="newQuestion"
          :placeholder="tr('research.ask_question_placeholder')"
          class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring"
        />
        <textarea
          v-model="newAnswer"
          rows="2"
          :placeholder="tr('research.optional_notes_placeholder')"
          class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring resize-y"
        ></textarea>
        <div class="flex justify-end">
          <button
            type="submit"
            :disabled="!newQuestion.trim() || submittingThread"
            class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-60 focus-ring text-sm"
          >
            <Send class="h-3.5 w-3.5" />
            {{ tr("research.save_thread") }}
          </button>
        </div>
      </form>

      <div v-if="threads.length === 0" class="text-sm text-ink-muted">
        {{ tr("research.no_threads") }}
      </div>
      <ul class="space-y-3">
        <li
          v-for="t in threads"
          :key="t.id"
          class="border border-subtle rounded-lg p-3 bg-surface-muted"
        >
          <div class="text-sm font-medium text-ink-primary">{{ t.question }}</div>
          <div v-if="t.answer" class="mt-1 text-sm text-ink-secondary whitespace-pre-wrap">
            {{ t.answer }}
          </div>
          <div class="mt-1 text-xs text-ink-muted">{{ t.created_at }}</div>
        </li>
      </ul>
    </section>

    <FilePreviewModal
      :file="previewFile"
      :preview-url="previewPdfUrl"
      :download-url="previewDocxUrl"
      :previewable-kinds="['pdf']"
      @close="closeMemoPreview"
    />
  </div>
</template>
