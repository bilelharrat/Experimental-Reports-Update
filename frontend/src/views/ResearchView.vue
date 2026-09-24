<script setup>
import { computed, defineAsyncComponent, inject, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  Building2,
  Download,
  Eye,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  Send,
  SlidersHorizontal,
} from "lucide-vue-next";
import { api, withApiToken } from "../api.js";
import AiMark from "../components/AiMark.vue";
import AutoUpdateBar from "../components/AutoUpdateBar.vue";
import { confirmTokenSpend } from "../confirmTokens.js";
import {
  formatCompactNumber,
  formatIsoDate,
  formatMetricValue,
  humanizeStatus,
  isPendingValue,
  isTerminalReportStatus,
} from "../formatters.js";
import { useT } from "../i18n.js";
import { lastPriceLabel, signedChange } from "../liveTicker.js";
import { POLL_MAX_FAILURES, pollDelayMs } from "../pollBackoff.js";
import { appLanguage, trackedCompanyIds } from "../state.js";
import { useLiveQuotes } from "../useLiveQuotes.js";
import CompanyDetail from "../components/CompanyDetail.vue";
import CompanyFollowButton from "../components/CompanyFollowButton.vue";
import Monogram from "../components/Monogram.vue";
import WarrenMark from "../components/WarrenMark.vue";
import { useLargeTitle } from "../chrome.js";
import CopilotDropZone from "../components/CopilotDropZone.vue";
import FilePreviewModal from "../components/FilePreviewModal.vue";
import MemoAnalysisDashboard from "../components/MemoAnalysisDashboard.vue";
import MemoStudioEditor from "../components/MemoStudioEditor.vue";
import UnifiedDocumentsView from "../components/UnifiedDocumentsView.vue";
import { buildDiscussPrompt, buildDiveDeeperPrompt } from "../copilotActions.js";
import { TARGET_KINDS } from "../copilotTargets.js";

// Lazy: the viewer pulls in docx-preview (~large); load it on first View.
const DocumentViewerDrawer = defineAsyncComponent(
  () => import("../components/DocumentViewerDrawer.vue"),
);

const tr = useT();
const openReportCustomizer = inject("openReportCustomizer", () => {});

// Backend returns canonical option strings (e.g. "Investment Memo (Late-Stage)",
// "Internal"). Map them to localized display labels here; unknown values fall
// through to the raw string so new server-side options keep working.
const REPORT_TYPE_ZH = {
  "Investment Report (Auto)": "投资报告（自动判断阶段）",
  "Investment Memo (Late-Stage)": "投资备忘录（Late-Stage / Pre-IPO）",
  "Buffett Investment Memo": "巴菲特方法备忘录",
  "Investment Report": "投资报告",
  Background: "背景研究",
  "Financial Analysis": "财务分析",
  "Market Analysis": "市场分析",
};
const AUDIENCE_ZH = {
  Internal: "内部",
  External: "外部",
  Assistant: "助理",
  Partner: "合伙人",
  LP: "LP",
};
const FUNDING_ROUND_ZH = {
  PreSeed: "Pre-Seed",
  "Pre-Seed": "Pre-Seed",
  Seed: "种子轮",
  "Series A": "A 轮",
  "Series B": "B 轮",
  "Series C": "C 轮",
  "Series D": "D 轮",
  Growth: "成长期",
  Public: "已上市",
};
const AUTO_REPORT_TYPE = "Investment Report (Auto)";
const BUFFETT_REPORT_TYPE = "Buffett Investment Memo";
const PRIMARY_REPORT_TYPES = new Set([
  AUTO_REPORT_TYPE,
  "Investment Memo (Late-Stage)",
  BUFFETT_REPORT_TYPE,
]);
// English display names that differ from the wire value (the wire value is
// what the API compares, so it never changes).
const REPORT_TYPE_EN = {
  "Buffett Investment Memo": "Buffett-Method Memo",
};
function reportTypeLabel(val) {
  if (appLanguage.value === "zh") return REPORT_TYPE_ZH[val] || val;
  return REPORT_TYPE_EN[val] || val;
}
function audienceLabel(val) {
  if (appLanguage.value === "zh") return AUDIENCE_ZH[val] || val;
  return val;
}
function fundingRoundLabel(val) {
  if (appLanguage.value === "zh") return FUNDING_ROUND_ZH[val] || val;
  return val;
}

const props = defineProps({ companyId: { type: String, required: true } });
const emit = defineEmits(["reports-changed", "open-copilot"]);

const route = useRoute();
const router = useRouter();
const companyTitleEl = ref(null);
useLargeTitle(companyTitleEl);

const company = ref(null);
const companyError = ref(null);
const options = ref({ report_types: [], audiences: [], languages: [] });
const newsFeed = ref({ rows: [], filters: { categories: [], tags: [] }, empty_state: "" });
const newsLoading = ref(false);
const newsError = ref("");
const newsCategory = ref("");
const newsSearch = ref("");
const newsSweeping = ref(false);
// The last sweep's outcome, shown under the filters so a fallback or a
// failed pass is visible rather than looking like an unchanged feed.
const newsSweep = ref(null);
const industryView = ref(null);
const industryLoading = ref(false);
const industryError = ref("");
const trackingUpdates = ref(null);
const trackingSyncing = ref(false);
const trackingSyncError = ref(false);
const executingAutoRunId = ref("");
const executeNotice = ref("");
// Set when Run now was blocked by a parked card review; renders the
// "I've reviewed — run anyway" confirmation next to the notice.
const pendingReviewRunId = ref("");
// Background sync schedule and the global auto-apply switch (off by
// default: recommended runs wait for Run now).
const trackingSettings = ref(null);
const trackingSettingsSaving = ref(false);
const decisionRecords = ref(null);
const decisionSubmitting = ref(false);
const decisionSubmitError = ref(false);
const decisionDeleteArmId = ref("");
const newDecisionVerdict = ref("invest");
const newDecisionExplanation = ref("");
const newDecisionDate = ref("");
const newDecisionReportId = ref("");
const refreshingCompany = ref(false);
const refreshCompanyError = ref("");

const isPublicCompany = computed(() => {
  const c = company.value;
  if (!c) return false;
  return String(c.company_type || "").trim().toLowerCase() === "public";
});
const canShowMemoStudio = computed(() =>
  Boolean(company.value && !isPublicCompany.value),
);
const companyTicker = computed(() =>
  String(company.value?.ticker || "").trim().toUpperCase(),
);
const companyQuoteTickers = computed(() =>
  companyTicker.value ? [companyTicker.value] : [],
);
const { quotes: companyQuotes } = useLiveQuotes(companyQuoteTickers);
const companyLiveQuote = computed(() => {
  const ticker = companyTicker.value;
  if (!ticker) return null;
  return companyQuotes.value?.[ticker] || null;
});
const companyQuoteLabel = computed(() => {
  const quote = companyLiveQuote.value;
  if (!quote || quote.last_price == null) return null;
  return lastPriceLabel({ last: quote.last_price, currency: quote.currency || "USD" });
});
const companyQuoteChange = computed(() => {
  const change = Number(companyLiveQuote.value?.change_pct_1d);
  return Number.isFinite(change) ? change : null;
});

// Default to the stage-calibrated auto memo: the agents decide whether
// the company reads early, late, or post-IPO and calibrate the framing.
const reportType = ref(AUTO_REPORT_TYPE);
const audience = ref("Internal");
const memoStage = ref("studio");
// Studio sub-sections (Basic = cards, Advanced = analysis workbench,
// Notes = saved Q&A).
const studioSection = ref("basic");
// One-Click generates everything in one shot; Studio Review pauses at
// the cards. Sticky per browser.
const GENERATION_MODE_KEY = "bsh.memoGenerationMode";
function loadGenerationMode() {
  try {
    const stored = localStorage.getItem(GENERATION_MODE_KEY);
    if (stored === "one_click" || stored === "studio_review") return stored;
  } catch {
    // Storage unavailable (private mode) — fall through to the default.
  }
  return "studio_review";
}
const generationMode = ref(loadGenerationMode());
watch(generationMode, (mode) => {
  try {
    localStorage.setItem(GENERATION_MODE_KEY, mode);
  } catch {
    // Best-effort persistence only.
  }
});

// Report length: "full" (the complete IC report) or "compact" (the
// short partner-style memo). Applies to One-Click generation.
const REPORT_MODE_KEY = "bsh.research.reportMode";
function loadReportMode() {
  try {
    const stored = localStorage.getItem(REPORT_MODE_KEY);
    if (stored === "full" || stored === "compact") return stored;
  } catch {
    // Storage unavailable — fall through to the default.
  }
  return "full";
}
const reportMode = ref(loadReportMode());
watch(reportMode, (mode) => {
  try {
    localStorage.setItem(REPORT_MODE_KEY, mode);
  } catch {
    // Best-effort persistence only.
  }
});

// Quality: "best" (every agent on the default model at full effort),
// "balanced" (research + translation on a cheaper model; writing on the
// default model at medium effort), or "economy" (everything on a cheaper
// model). Applies to One-Click generation.
const QUALITY_KEY = "bsh.research.quality";
function loadQuality() {
  try {
    const stored = localStorage.getItem(QUALITY_KEY);
    if (["best", "balanced", "economy"].includes(stored)) return stored;
  } catch {
    // Storage unavailable — fall through to the default.
  }
  return "best";
}
const quality = ref(loadQuality());
watch(quality, (level) => {
  try {
    localStorage.setItem(QUALITY_KEY, level);
  } catch {
    // Best-effort persistence only.
  }
});

const activeReport = ref(null);
const companyReports = ref([]);
const generationError = ref(null);
const resuming = ref(false);
const startingFresh = ref(false);
const dismissing = ref(false);
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
    // A parked studio investigation is a deliberate resting state — the
    // user edits cards, then generates.
    status === "awaiting_studio" ||
    status.startsWith("failed");
  return !terminal;
});

// Memo report — language toggle for the preview pane.
const previewLanguage = ref("en");
function isMemoKind(kind) {
  return (
    kind === "investment_memo_latestage" || kind === "buffett_investment_memo"
  );
}
function isMemoReportType(reportTypeValue) {
  return PRIMARY_REPORT_TYPES.has(reportTypeValue);
}
const isMemo = computed(() => isMemoKind(activeReport.value?.kind));
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
// A failed report is a historical record — without a timestamp the banner
// reads as a live error, even days later. Label it with when it failed.
const reportFailedAtLabel = computed(() => {
  const raw = activeReport.value?.updated_at || activeReport.value?.created_at;
  if (!raw) return "";
  const failedAt = Date.parse(raw);
  if (Number.isNaN(failedAt)) return "";
  return new Date(failedAt).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
});
const reportIsFailed = computed(() =>
  String(activeReport.value?.status || "").startsWith("failed"),
);
const rendererContractErrors = computed(() => {
  const errors = activeReport.value?.renderer_contract?.errors;
  return Array.isArray(errors) ? errors : [];
});
const rendererContractFiles = computed(() => {
  const files = activeReport.value?.renderer_contract?.expected_files;
  return Array.isArray(files) ? files : [];
});
const reportHasWarnings = computed(
  () => String(activeReport.value?.status || "") === "complete_with_warnings",
);
const canResumeMemo = computed(() =>
  Boolean(
    isMemo.value &&
      (reportIsFailed.value || reportHasWarnings.value) &&
      activeReport.value?.resume_available,
  ),
);
// The report to surface when none is deep-linked. A parked studio
// investigation is durable state on disk (Phase-2 artifacts + spine in
// the run folder): after a reload or server restart the next step is
// still just "Generate Report", never a re-investigation. Failed studio
// runs surface for the same reason (Generate again / re-investigate),
// and resumable failures keep their existing behavior.
const latestActionableMemoReport = computed(() => {
  const reports = Array.isArray(companyReports.value) ? companyReports.value : [];
  return (
    [...reports]
      .filter((report) => {
        if (!report?.kind || !isMemoKind(report.kind)) return false;
        if (report.dismissed_at || report.superseded_by) return false;
        const status = String(report.status || "");
        if (status === "awaiting_studio") return true;
        if (
          report.memo_mode === "studio" &&
          status.startsWith("failed") &&
          status !== "failed_scope_check"
        ) {
          return true;
        }
        return Boolean(
          report.resume_available &&
            (status.startsWith("failed") ||
              status === "complete_with_warnings"),
        );
      })
      .sort((a, b) =>
        String(b.updated_at || b.created_at || "").localeCompare(
          String(a.updated_at || a.created_at || ""),
        ),
      )[0] || null
  );
});
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
  if (reportIsFailed.value) return reportFailureTitle.value;
  if (r.status === "awaiting_studio") return tr("research.status_cards_ready");
  if (reportInProgress.value || generating.value) return tr("research.status_running");
  if (reportHasWarnings.value) return tr("research.status_needs_attention");
  if (r.status === "complete") return tr("research.status_ready");
  return r.stage || humanizeStatus(r.status) || "";
});
const reportUserStatus = computed(() => {
  if (activeReport.value?.status === "awaiting_studio") return "cards_ready";
  if (generating.value || reportInProgress.value) return "running";
  if (reportIsFailed.value) return "failed";
  if (reportHasWarnings.value) return "needs_attention";
  if (activeReport.value?.status === "complete") return "ready";
  return "";
});
const reportUserStatusLabel = computed(() => {
  const status = reportUserStatus.value;
  if (status === "running") return tr("research.status_running");
  if (status === "cards_ready") return tr("research.status_cards_ready");
  if (status === "failed") return tr("research.status_failed");
  if (status === "needs_attention") return tr("research.status_needs_attention");
  if (status === "ready") return tr("research.status_ready");
  return "";
});
const analysisArtifacts = computed(() => {
  const artifacts = activeReport.value?.analysis_artifacts;
  return Array.isArray(artifacts) ? artifacts : [];
});
// Slide-in document viewer for the analysis markdown artifacts.
const docViewer = ref(null);
function openArtifactViewer(artifact) {
  if (!artifact?.download_url) return;
  docViewer.value = {
    title: artifact.label || artifact.filename || "",
    sources: [
      {
        key: "MD",
        url: withApiToken(artifact.download_url),
        kind: "md",
      },
    ],
  };
}
function openMemoDocViewer() {
  const r = activeReport.value;
  if (!r) return;
  const rawUrls = r.download_urls || {};
  const order = { en: 0, zh: 1, internal: 2 };
  const sources = Object.keys(rawUrls)
    .sort((a, b) => (order[a] ?? 9) - (order[b] ?? 9))
    .map((k) => ({
      key: String(k).toUpperCase(),
      url: withApiToken(rawUrls[k]),
      kind: "docx",
    }));
  if (!sources.length) return;
  const name = r.company_name || company.value?.name || "Memo";
  docViewer.value = {
    title: `${name} — ${tr("research.tab_memo")}`,
    sources,
  };
}
function closeDocViewer() {
  docViewer.value = null;
}
const gateDiagnostics = computed(() => {
  const r = activeReport.value;
  if (!r) return [];
  const items = [];
  const add = (label, payload) => {
    if (!payload || typeof payload !== "object") return;
    items.push({
      label,
      status: payload.status || "",
      p0Count: Number(payload.p0_count || 0),
      findingCount: Number(payload.finding_count || 0),
    });
  };
  add(tr("research.gate_quality"), r.memo_quality_lint);
  add(tr("research.gate_chinese_parity"), r.memo_chinese_parity);
  add(tr("research.gate_fact_check"), r.memo_fact_check);
  return items;
});
const gateFindings = computed(() => {
  const r = activeReport.value;
  if (!r) return [];
  const gates = [
    [tr("research.gate_quality"), r.memo_quality_lint],
    [tr("research.gate_chinese_parity"), r.memo_chinese_parity],
    [tr("research.gate_fact_check"), r.memo_fact_check],
  ];
  return gates.flatMap(([gateLabel, payload]) => {
    const findings = payload?.findings;
    if (!Array.isArray(findings)) return [];
    return findings
      .filter((finding) => finding && typeof finding === "object")
      .map((finding) => ({ ...finding, gateLabel }));
  });
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
      r.artifacts_available ||
      r.content_en ||
      r.content_zh,
  );
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
const submitThreadError = ref("");

const libraryRefresh = ref(0);

const TAB_IDS = ["overview", "documents", "memo", "news", "decisions"];
function normalizeTabName(raw) {
  // Legacy Evidence umbrella → Files. Analysis/console deep-links open Report.
  if (raw === "evidence") return "documents";
  if (raw === "analysis") return "memo";
  if (raw === "industry") return "overview";
  if (raw === "console") {
    emit("open-copilot");
    return "memo";
  }
  if (!raw && route.query.report) return "memo";
  return TAB_IDS.includes(raw) ? raw : "overview";
}

const activeTab = ref(normalizeTabName(route.query.tab));
function switchTab(name) {
  const nextTab =
    name === "memo" && company.value && !canShowMemoStudio.value
      ? "overview"
      : name;
  activeTab.value = nextTab;
  const nextQuery = { ...route.query };
  if (nextTab === "overview") delete nextQuery.tab;
  else nextQuery.tab = nextTab;
  router.replace({
    name: "research",
    params: { companyId: props.companyId },
    query: nextQuery,
  });
}
watch(
  () => [route.query.tab, route.query.report],
  ([tab]) => {
    activeTab.value = normalizeTabName(tab);
  },
);
watch(
  () => route.query.files,
  (token) => {
    if (token) libraryRefresh.value += 1;
  },
);
function normalizeActiveTabForCompany() {
  if (activeTab.value === "memo" && company.value && !canShowMemoStudio.value) {
    switchTab("overview");
  }
}
watch(
  [activeTab, canShowMemoStudio, () => company.value?.id],
  normalizeActiveTabForCompany,
);

// Flat company strip — no nested Evidence sub-tabs.
const workspaceTabs = computed(() => [
  { id: "overview", label: tr("research.tab_overview"), show: true },
  { id: "documents", label: tr("research.tab_documents"), show: true },
  { id: "memo", label: tr("research.tab_memo"), show: canShowMemoStudio.value },
  { id: "news", label: tr("research.tab_news_updates"), show: true },
  { id: "decisions", label: tr("research.tab_decisions"), show: true },
]);

const primaryReportTypes = computed(() => {
  const types = options.value.report_types || [];
  const primary = types.filter((type) => PRIMARY_REPORT_TYPES.has(type));
  return primary.length ? primary : types;
});
const moreReportTypes = computed(() => {
  const types = options.value.report_types || [];
  if (!types.some((type) => PRIMARY_REPORT_TYPES.has(type))) return [];
  return types.filter((type) => !PRIMARY_REPORT_TYPES.has(type));
});

const hasReportContext = computed(() => {
  if (activeReport.value) return true;
  return (companyReports.value || []).some((report) => isMemoKind(report?.kind));
});

const memoStages = computed(() => [
  {
    id: "studio",
    label: tr("research.memo_stage_studio"),
    enabled: true,
  },
  {
    id: "preview",
    label: tr("research.memo_stage_preview"),
    enabled: hasReportContext.value,
  },
]);

const studioSections = computed(() => [
  { id: "basic", label: tr("research.studio_section_basic") },
  { id: "advanced", label: tr("research.studio_section_advanced") },
  { id: "notes", label: tr("research.memo_stage_notes") },
]);

function memoStageEnabled(id) {
  const stage = memoStages.value.find((item) => item.id === id);
  return Boolean(stage?.enabled);
}

// A fresh ?report= deep link (Files library "Generated memos" rows)
// means "show me this document". The flag is consumed on first use so
// clicking the Report tab afterwards lands on Studio, not Document.
const pendingReportDeepLink = ref(
  route.query.report ? String(route.query.report) : "",
);
watch(
  () => route.query.report,
  (value) => {
    pendingReportDeepLink.value = value ? String(value) : "";
  },
);

function defaultMemoStage() {
  if (reportIsFailed.value || reportHasWarnings.value) return "studio";
  if (
    pendingReportDeepLink.value &&
    activeReport.value?.id === pendingReportDeepLink.value &&
    memoArtifactsVisible.value &&
    !generating.value
  ) {
    pendingReportDeepLink.value = "";
    return "preview";
  }
  return "studio";
}

function askCopilotPrompt() {
  const name = company.value?.name || tr("app.company");
  const report = activeReport.value;
  if (report?.report_type) {
    return tr("research.ask_copilot_prompt_report", {
      name,
      type: reportTypeLabel(report.report_type),
    });
  }
  return tr("research.ask_copilot_prompt", { name });
}

function openAskInCopilot() {
  emit("open-copilot", askCopilotPrompt());
}

function setMemoStage(id) {
  if (!memoStageEnabled(id)) return;
  memoStage.value = id;
}

function setStudioSection(id) {
  if (studioSections.value.some((section) => section.id === id)) {
    studioSection.value = id;
  }
}

watch(
  [activeTab, () => route.query.tab, () => activeReport.value?.id, hasReportContext],
  () => {
    if (activeTab.value !== "memo") return;
    // Legacy deep link: ?tab=analysis used to open the Analysis stage —
    // that panel now lives under Studio → Advanced.
    if (route.query.tab === "analysis") {
      memoStage.value = "studio";
      studioSection.value = "advanced";
      return;
    }
    if (route.query.tab === "console") {
      openAskInCopilot();
      memoStage.value = defaultMemoStage();
      return;
    }
    const next = defaultMemoStage();
    memoStage.value = memoStageEnabled(next) ? next : "studio";
  },
  { immediate: true },
);
watch(generating, (isGenerating, wasGenerating) => {
  if (wasGenerating && !isGenerating && activeTab.value === "memo") {
    if (activeReport.value?.status === "complete" || reportHasWarnings.value) {
      setMemoStage("preview");
    }
  }
});
watch(memoStage, (stage) => {
  if (!memoStageEnabled(stage)) memoStage.value = "studio";
});

const companyNews = computed(() => {
  const c = company.value || {};
  const rows = Array.isArray(newsFeed.value?.rows) && newsFeed.value.rows.length
    ? newsFeed.value.rows
    : Array.isArray(c.company_news) && c.company_news.length
      ? c.company_news
      : c.recent_news || [];
  return [...rows].sort((a, b) =>
    String(b.published_at || b.date || "").localeCompare(
      String(a.published_at || a.date || ""),
    ),
  );
});

const NEWS_FILTERS = [
  { value: "", labelKey: "research.news_filter_all" },
  { value: "filings", labelKey: "research.news_filter_filings" },
  { value: "funding", labelKey: "research.news_filter_funding" },
  { value: "product", labelKey: "research.news_filter_product" },
  { value: "press", labelKey: "research.news_filter_press" },
];

function selectNewsCategory(value) {
  newsCategory.value = value;
}

const industryMetrics = computed(() => {
  const metrics = industryView.value?.metrics || company.value?.industry_view?.metrics;
  return Array.isArray(metrics) ? metrics : [];
});

const industryMetricSlots = computed(() => {
  const rows = industryMetrics.value;
  const defaults = [
    { label: "TAM" },
    { label: "CAGR" },
    { label: tr("research.industry_public_comps") },
    { label: "EV / Revenue" },
  ];
  return defaults.map((fallback, index) => rows[index] || fallback);
});

const expertOpinions = computed(() => {
  const opinions = industryView.value?.expert_opinions || company.value?.expert_opinions;
  return Array.isArray(opinions) ? opinions : [];
});

const publicComps = computed(() => {
  const rows = industryView.value?.public_comps;
  return Array.isArray(rows) ? rows : [];
});

const sectorSignals = computed(() => {
  const rows = industryView.value?.sector_signals || company.value?.industry_view?.sector_signals;
  return Array.isArray(rows) ? rows : [];
});

let pollId = null;
let pollActive = false;
let pollFailures = 0;
const pollConnectionLost = ref(false);

const reportInProgress = computed(() =>
  Boolean(activeReport.value) &&
  !isTerminalReportStatus(activeReport.value?.status),
);

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
function requestErrorPayload(e) {
  return {
    message: e?.message || String(e),
    status: e?.status ?? null,
  };
}

function monogram(name) {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function translatedCompanyField(field) {
  const c = company.value || {};
  const sourceIsZh = c.language === "zh";
  const needsTranslation = c.translation && (
    (appLanguage.value === "zh" && !sourceIsZh) ||
    (appLanguage.value === "en" && sourceIsZh)
  );
  if (needsTranslation && c.translation?.[field]) return c.translation[field];
  return c[field];
}

const companyWebsiteHref = computed(() => {
  const website = company.value?.website;
  if (!website) return "";
  return /^https?:\/\//i.test(website) ? website : `https://${website}`;
});

const companyPositioning = computed(() => {
  const c = company.value || {};
  const p = c.positioning || {};
  if (p.category || p.customers || p.need || p.benefit || p.differentiator) {
    return {
      category: p.category || tr("research.positioning_company"),
      customers: p.customers || tr("research.positioning_customers"),
      need: p.need || tr("research.positioning_need"),
      benefit: p.benefit || tr("research.positioning_benefit"),
      alternative: p.alternative || tr("research.positioning_alternative"),
      differentiator: p.differentiator || tr("research.positioning_differentiator"),
    };
  }
  return null;
});

const companyPositioningFallback = computed(() => {
  const text = translatedCompanyField("description") || tr("research.positioning_pending");
  const splitAt = text.indexOf(",");
  if (splitAt > 14) {
    return {
      lead: text.slice(0, splitAt + 1),
      body: text.slice(splitAt + 1).trim(),
    };
  }
  return { lead: company.value?.name || "", body: text };
});

async function refreshCompanyRecord() {
  if (!company.value || refreshingCompany.value) return;
  if (!confirmTokenSpend()) return;
  refreshingCompany.value = true;
  refreshCompanyError.value = "";
  try {
    company.value = await api.refreshCompany(company.value.id);
  } catch {
    refreshCompanyError.value = tr("company.refresh_failed");
  } finally {
    refreshingCompany.value = false;
  }
}

function fundingAmount(value) {
  return formatCompactNumber(value, { currency: true });
}

function newsMeta(item) {
  return [
    item.source || item.provenance?.origin,
    item.category,
    formatIsoDate(item.published_at || item.date, ""),
  ].filter(Boolean).join(" · ");
}

async function loadCompany() {
  companyError.value = null;
  const requestedId = props.companyId;
  try {
    const fresh = await api.getCompany(requestedId);
    // Stale-response guard: on rapid navigation an earlier, slower
    // response can resolve last and clobber the newer company's state.
    if (requestedId !== props.companyId) return;
    company.value = fresh;
    await Promise.allSettled([
      loadNewsFeed(),
      loadIndustryView(),
      loadTrackingUpdates(),
      loadDecisionRecords(),
    ]);
  } catch (e) {
    if (requestedId !== props.companyId) return;
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

async function loadNewsFeed() {
  if (!props.companyId) return;
  newsLoading.value = true;
  newsError.value = "";
  try {
    newsFeed.value = await api.getCompanyNewsFeed(props.companyId, {
      category: newsCategory.value,
      search: newsSearch.value,
      lang: appLanguage.value,
    });
  } catch {
    newsError.value = "load";
    newsFeed.value = { rows: [], filters: { categories: [], tags: [] }, empty_state: "" };
  } finally {
    newsLoading.value = false;
  }
}

async function sweepNewsFeed() {
  if (!props.companyId || newsSweeping.value) return;
  newsSweeping.value = true;
  newsSweep.value = null;
  try {
    const feed = await api.refreshCompanyNewsFeed(props.companyId, appLanguage.value);
    newsSweep.value = feed?.sweep || null;
    // The refresh returns the unfiltered feed; reload so the active
    // category and search still apply to what the user sees.
    await loadNewsFeed();
  } catch (e) {
    newsSweep.value = { error: e?.message || String(e), added: 0 };
  } finally {
    newsSweeping.value = false;
  }
}

async function loadIndustryView() {
  if (!props.companyId) return;
  industryLoading.value = true;
  industryError.value = "";
  try {
    industryView.value = await api.getCompanyIndustryView(props.companyId);
  } catch {
    industryError.value = "load";
    industryView.value = null;
  } finally {
    industryLoading.value = false;
  }
}

async function loadTrackingUpdates() {
  if (!props.companyId) return;
  const requestedId = props.companyId;
  loadTrackingSettings();
  loadTrackedAutoUpdate();
  try {
    const fresh = await api.listTrackingUpdates(requestedId);
    if (requestedId !== props.companyId) return;
    trackingUpdates.value = fresh;
  } catch {
    // Non-fatal: the panel keeps whatever it already shows.
  }
}

async function loadTrackingSettings() {
  try {
    trackingSettings.value = await api.getTrackingSettings();
  } catch {
    // Non-fatal: the auto-apply toggle stays disabled until settings load.
  }
}

const trackedAutoUpdate = ref(null);

async function loadTrackedAutoUpdate() {
  try {
    const payload = await api.getAutoUpdates();
    trackedAutoUpdate.value =
      (payload.channels || []).find((row) => row.id === "tracked_news") || null;
  } catch {
    trackedAutoUpdate.value = null;
  }
}

function onTrackedCadenceSaved(channel) {
  trackedAutoUpdate.value = channel;
  loadTrackingSettings();
}

function onTrackedCadenceError() {
  executeNotice.value = tr("auto_update.save_failed");
}

async function toggleAutoApply() {
  if (trackingSettingsSaving.value || !trackingSettings.value) return;
  const next = !trackingSettings.value.auto_apply;
  // Turning it on lets news start paid runs unattended, so confirm first.
  if (next && !window.confirm(tr("research.updates_auto_apply_confirm"))) return;
  trackingSettingsSaving.value = true;
  executeNotice.value = "";
  try {
    trackingSettings.value = await api.putTrackingSettings({ auto_apply: next });
  } catch {
    executeNotice.value = tr("research.updates_auto_apply_failed");
  } finally {
    trackingSettingsSaving.value = false;
  }
}

const trackingScheduleLabel = computed(() => {
  const settings = trackingSettings.value;
  if (!settings) return "";
  // 0 hours means the cadence bar is on Manual: nothing checks on its own.
  const hours = Number(settings.interval_hours) || 0;
  if (hours <= 0) {
    return tr(
      settings.auto_apply
        ? "research.updates_schedule_off_auto"
        : "research.updates_schedule_off_manual",
    );
  }
  return tr(
    settings.auto_apply
      ? "research.updates_schedule_auto"
      : "research.updates_schedule_manual",
    { hours },
  );
});

async function loadDecisionRecords() {
  if (!props.companyId) return;
  const requestedId = props.companyId;
  try {
    const fresh = await api.decisionRecords.list(requestedId);
    if (requestedId !== props.companyId) return;
    decisionRecords.value = fresh;
  } catch {
    // Non-fatal: the tab keeps whatever it already shows.
  }
}

async function submitDecision() {
  if (decisionSubmitting.value || !newDecisionExplanation.value.trim()) return;
  decisionSubmitting.value = true;
  decisionSubmitError.value = false;
  try {
    await api.decisionRecords.add(props.companyId, {
      verdict: newDecisionVerdict.value,
      explanation: newDecisionExplanation.value.trim(),
      decided_at: newDecisionDate.value || null,
      report_id: newDecisionReportId.value || null,
    });
    newDecisionExplanation.value = "";
    newDecisionDate.value = "";
    newDecisionReportId.value = "";
    await loadDecisionRecords();
  } catch {
    decisionSubmitError.value = true;
  } finally {
    decisionSubmitting.value = false;
  }
}

async function removeDecision(decisionId) {
  if (decisionDeleteArmId.value !== decisionId) {
    decisionDeleteArmId.value = decisionId;
    return;
  }
  decisionDeleteArmId.value = "";
  try {
    await api.decisionRecords.remove(props.companyId, decisionId);
    await loadDecisionRecords();
  } catch {
    decisionSubmitError.value = true;
  }
}

function decisionChipClass(verdict) {
  const base = "rounded-pill px-2 py-0.5 text-caption1 font-medium";
  if (verdict === "invest") return `${base} bg-success-soft text-success-ink`;
  if (verdict === "pass") return `${base} bg-danger/15 text-danger`;
  return `${base} bg-warning/15 text-warning`;
}

function decisionVerdictLabel(verdict) {
  const keys = {
    invest: "research.decision_verdict_invest",
    pass: "research.decision_verdict_pass",
    watch: "research.decision_verdict_watch",
  };
  return keys[verdict] ? tr(keys[verdict]) : verdict;
}

function retroChipClass(verdict) {
  const base = "rounded-pill px-2 py-0.5 text-caption1 font-medium";
  if (verdict === "still_right") return `${base} bg-success-soft text-success-ink`;
  if (verdict === "looks_wrong") return `${base} bg-danger/15 text-danger`;
  return `${base} bg-warning/15 text-warning`;
}

function retroVerdictLabel(verdict) {
  const keys = {
    still_right: "research.decision_retro_still_right",
    questionable: "research.decision_retro_questionable",
    looks_wrong: "research.decision_retro_looks_wrong",
  };
  return keys[verdict] ? tr(keys[verdict]) : verdict;
}

function retroRationale(retro) {
  if (appLanguage.value === "zh") {
    return retro?.rationale_zh || retro?.rationale_en || "";
  }
  return retro?.rationale_en || retro?.rationale_zh || "";
}

function decisionLinkedReport(row) {
  if (!row?.report_id) return null;
  return (
    (companyReports.value || []).find((r) => r.id === row.report_id) || {
      id: row.report_id,
    }
  );
}

async function syncTracking() {
  if (trackingSyncing.value || !props.companyId) return;
  if (!confirmTokenSpend()) return;
  trackingSyncing.value = true;
  trackingSyncError.value = false;
  executeNotice.value = "";
  pendingReviewRunId.value = "";
  try {
    trackingUpdates.value = await api.syncTrackingUpdates(props.companyId, {
      mark_auto: true,
      execute: false,
      refresh_news: true,
      lang: appLanguage.value,
    });
    // The sync's news refresh may have added feed rows.
    await loadNewsFeed();
  } catch {
    trackingSyncError.value = true;
  } finally {
    trackingSyncing.value = false;
  }
}

const EXECUTE_NOTICE_KEYS = {
  company_busy: "research.updates_execute_busy",
  auto_run_not_recommended: "research.updates_execute_not_recommended",
  no_recommended_auto_run: "research.updates_execute_none",
  action_none: "research.updates_execute_none",
  awaiting_studio_review: "research.updates_execute_awaiting_studio",
  studio_requires_parallel: "research.updates_execute_needs_parallel",
  run_slots_full: "research.updates_execute_slots_full",
};

async function runAutoRun(run, { acknowledgeReview = false } = {}) {
  if (executingAutoRunId.value) return;
  executingAutoRunId.value = run.id;
  executeNotice.value = "";
  pendingReviewRunId.value = "";
  try {
    const result = await api.executeTrackingAutoRun(props.companyId, run.id, {
      acknowledge_review: acknowledgeReview,
    });
    if (result?.executed) {
      await loadTrackingUpdates();
      if (result.report_id) {
        // Same navigation as opening a report from the library: the
        // report query drives the Report tab + polling machinery.
        router.replace({
          name: "research",
          params: { companyId: props.companyId },
          query: { report: result.report_id },
        });
      }
    } else {
      executeNotice.value = tr(
        EXECUTE_NOTICE_KEYS[result?.reason] || "research.updates_execute_failed",
      );
      if (result?.reason === "awaiting_studio_review") {
        pendingReviewRunId.value = run.id;
      }
      await loadTrackingUpdates();
    }
  } catch {
    executeNotice.value = tr("research.updates_execute_failed");
  } finally {
    executingAutoRunId.value = "";
  }
}

function confirmReviewedAndRun() {
  const runId = pendingReviewRunId.value;
  const run = (trackingUpdates.value?.auto_runs || []).find(
    (row) => row.id === runId,
  );
  if (run) runAutoRun(run, { acknowledgeReview: true });
  else pendingReviewRunId.value = "";
}

const isFollowedCompany = computed(() =>
  trackedCompanyIds.value.has(String(company.value?.id || props.companyId || "")),
);

function impactChipClass(impact) {
  const base = "rounded-pill px-2 py-0.5 text-caption1 font-medium";
  if (impact === "high") return `${base} bg-danger/15 text-danger`;
  if (impact === "medium") return `${base} bg-warning/15 text-warning`;
  return `${base} bg-fill-tertiary text-ink-secondary`;
}

function impactLabel(impact) {
  if (impact === "high") return tr("research.impact_high");
  if (impact === "medium") return tr("research.impact_medium");
  return tr("research.impact_low");
}

const AUTO_RUN_STATUS_KEYS = {
  recommended: "research.auto_run_recommended",
  running: "research.auto_run_running",
  completed: "research.auto_run_completed",
  failed: "research.auto_run_failed",
};

function autoRunStatusLabel(run) {
  const key = AUTO_RUN_STATUS_KEYS[run?.status];
  return key ? tr(key) : String(run?.status || "");
}

function autoRunStatusChipClass(status) {
  const base = "rounded-pill px-2 py-0.5 text-caption1 font-semibold";
  if (status === "running") return `${base} bg-accent-soft text-accent-ink`;
  if (status === "failed") return `${base} bg-danger/15 text-danger`;
  if (status === "recommended") return `${base} bg-warning/15 text-warning`;
  return `${base} bg-fill-tertiary text-ink-secondary`;
}

// Tracked items keyed by url (preferred) and title, so the existing
// feed rows can carry impact chips instead of rendering a second list.
const trackedImpactByKey = computed(() => {
  const map = new Map();
  for (const item of trackingUpdates.value?.items || []) {
    const url = String(item.url || "").trim().toLowerCase();
    const title = String(item.title || "").trim().toLowerCase();
    if (url) map.set(url, item);
    if (title) map.set(`t:${title}`, item);
  }
  return map;
});

function feedItemImpact(item) {
  const map = trackedImpactByKey.value;
  const url = String(item?.url || item?.archive_url || "").trim().toLowerCase();
  if (url && map.has(url)) return map.get(url);
  const title = String(item?.title || item?.headline || "").trim().toLowerCase();
  if (title && map.has(`t:${title}`)) return map.get(`t:${title}`);
  return null;
}

const activeReportAutoRunLabel = computed(() => {
  if (activeReport.value?.trigger !== "tracking_auto_run") return "";
  const runId = activeReport.value?.auto_run_id;
  const match = (trackingUpdates.value?.auto_runs || []).find(
    (run) => run.id === runId,
  );
  const label = String(match?.label || "");
  return label.length > 60 ? `${label.slice(0, 60)}…` : label;
});

watch(newsCategory, () => {
  if (company.value) loadNewsFeed();
});

// Re-fetch news content in the new language when the user toggles 中/EN.
watch(appLanguage, () => {
  if (company.value) loadNewsFeed();
});

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
    pollFailures = 0;
    pollConnectionLost.value = false;
    activeReport.value = r;
    const status = String(r.status || "");
    if (
      status === "complete" ||
      status === "complete_with_warnings" ||
      status === "awaiting_studio" ||
      status.startsWith("failed")
    ) {
      stopPolling();
      await loadCompanyReports();
      // Flip any auto-run chip (running → completed/failed) and the
      // Overview auto-updated badge without a dedicated poll loop.
      loadTrackingUpdates();
      if (status === "complete" || status === "complete_with_warnings") {
        emit("reports-changed");
        libraryRefresh.value += 1;
      }
    }
  } catch (e) {
    // A transient blip (dev-server reload, laptop sleep, a read racing a
    // write) must not permanently freeze a 30-minute run's progress UI.
    // Back off and only give up after several consecutive failures.
    pollFailures += 1;
    if (pollFailures >= POLL_MAX_FAILURES) {
      stopPolling();
      pollConnectionLost.value = true;
    }
  }
}

async function openReportFromLibrary(r) {
  router.replace({
    name: "research",
    params: { companyId: props.companyId },
    query: { report: r.id },
  });
}

// SSE is the primary live channel for memo progress (it replays
// stream.jsonl from the start, so a mid-run reload recovers history).
// The bounded-retry poll stays as a slow safety net while the stream is
// healthy and becomes the sole channel if the stream errors.
let memoStream = null;
let streamRefreshTimer = null;

function openMemoStream() {
  if (memoStream || !isMemo.value || !activeReport.value?.id) return;
  if (typeof EventSource === "undefined") return;
  try {
    memoStream = new EventSource(
      withApiToken(`/api/memos/${activeReport.value.id}/stream`),
    );
  } catch {
    memoStream = null;
    return;
  }
  memoStream.onmessage = (msg) => {
    let terminal = false;
    try {
      const entry = JSON.parse(msg.data);
      terminal = entry.type === "done" || entry.type === "error";
    } catch {
      // Non-JSON lines still count as liveness.
    }
    if (terminal) {
      closeMemoStream();
      pollReport();
      return;
    }
    // Stream traffic proves the run is alive — refresh the report record
    // (debounced) so stage/progress track without 1/s polling.
    if (!streamRefreshTimer) {
      streamRefreshTimer = setTimeout(() => {
        streamRefreshTimer = null;
        pollReport();
      }, 2000);
    }
  };
  memoStream.onerror = () => {
    // Stream lost — the poll loop below takes over at full cadence.
    closeMemoStream();
  };
}

function closeMemoStream() {
  if (streamRefreshTimer) {
    clearTimeout(streamRefreshTimer);
    streamRefreshTimer = null;
  }
  if (memoStream) {
    memoStream.close();
    memoStream = null;
  }
}

function scheduleNextPoll() {
  if (!pollActive) return;
  // While the SSE stream is healthy the poll is only a safety net.
  const delay = memoStream ? 15000 : pollDelayMs(pollFailures);
  pollId = setTimeout(async () => {
    await pollReport();
    scheduleNextPoll();
  }, delay);
}

function startPolling() {
  stopPolling();
  pollActive = true;
  pollFailures = 0;
  pollConnectionLost.value = false;
  openMemoStream();
  scheduleNextPoll();
}
function stopPolling() {
  pollActive = false;
  closeMemoStream();
  if (pollId) clearTimeout(pollId);
  pollId = null;
}

async function generate(analysisSessionId = null) {
  const memoAnalysisSessionId =
    typeof analysisSessionId === "string" ? analysisSessionId : null;
  generationError.value = null;
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
      report_mode: reportMode.value,
      quality: quality.value,
    });
    activeReport.value = r;
    await loadCompanyReports();
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
    generationError.value = requestErrorPayload(e);
    try {
      await loadCompanyReports();
    } catch {
      // Keep the original generate failure visible.
    }
  } finally {
    startingFresh.value = false;
  }
}

// ---- Memo Studio flow -----------------------------------------------------

const isStudioReport = computed(
  () => activeReport.value?.memo_mode === "studio",
);
const awaitingStudio = computed(
  () => isStudioReport.value && activeReport.value?.status === "awaiting_studio",
);
// A failed studio GENERATION recovers by pressing Generate again (the
// composed spine is on disk); a failed investigation starts over.
const studioGenerateRecoverable = computed(() => {
  const r = activeReport.value;
  return (
    isStudioReport.value &&
    r?.status === "failed_during_analysis" &&
    r?.failure_phase === "studio_generate"
  );
});
const studioRegenerateAvailable = computed(() => {
  const r = activeReport.value;
  return (
    isStudioReport.value &&
    (r?.status === "complete" || r?.status === "complete_with_warnings")
  );
});
// Studio Review needs the spine-lite pipeline; Buffett stays One-Click.
const studioReviewAvailable = computed(
  () =>
    isMemoReportType(reportType.value) &&
    reportType.value !== BUFFETT_REPORT_TYPE,
);
const studioInvestigationDate = computed(() => {
  const completed = activeReport.value?.studio_investigation?.completed_at;
  return completed ? formatIsoDate(completed) : "";
});

const studioCta = computed(() => {
  if (generating.value) {
    return { kind: "busy", label: tr("research.generating") };
  }
  if (awaitingStudio.value || studioGenerateRecoverable.value) {
    return {
      kind: "generate_studio",
      label: tr("research.generate_report_button"),
    };
  }
  if (generationMode.value === "studio_review" && studioReviewAvailable.value) {
    return {
      kind: "investigate",
      label: tr("research.deep_investigate_button"),
    };
  }
  return { kind: "one_click", label: tr("research.generate_button") };
});

function runStudioCta() {
  const kind = studioCta.value.kind;
  if (kind === "busy") return;
  if (kind === "generate_studio") return generateFromStudio();
  if (kind === "investigate") return startDeepInvestigate();
  return generate();
}

async function startDeepInvestigate() {
  generationError.value = null;
  startingFresh.value = true;
  try {
    const r = await api.studioInvestigate({
      company_id: props.companyId,
      report_type: reportType.value,
    });
    activeReport.value = r;
    await loadCompanyReports();
    router.replace({
      name: "research",
      params: { companyId: props.companyId },
      query: { report: r.id },
    });
    emit("reports-changed");
    startPolling();
  } catch (e) {
    generationError.value = requestErrorPayload(e);
    try {
      await loadCompanyReports();
    } catch {
      // Keep the original failure visible.
    }
  } finally {
    startingFresh.value = false;
  }
}

async function generateFromStudio() {
  const reportId = activeReport.value?.id;
  if (!reportId || !isStudioReport.value) return;
  generationError.value = null;
  startingFresh.value = true;
  try {
    const r = await api.studioGenerate(reportId);
    activeReport.value = r;
    await loadCompanyReports();
    emit("reports-changed");
    startPolling();
  } catch (e) {
    generationError.value = requestErrorPayload(e);
  } finally {
    startingFresh.value = false;
  }
}

function openMemoEditorDiscuss(context) {
  const prompt = context?.dive_deeper
    ? buildDiveDeeperPrompt(context)
    : buildDiscussPrompt(context);
  emit("open-copilot", {
    prompt,
    context: {
      surface: "memo_studio",
      tab: "memo",
      selection: context || {},
    },
  });
}

async function handleDocumentsChanged() {
  libraryRefresh.value += 1;
  // Deleting a generated report from the Library must not leave a stale
  // viewer: refresh the report list and drop the active report if gone.
  await loadCompanyReports();
  const reports = Array.isArray(companyReports.value) ? companyReports.value : [];
  if (activeReport.value && !reports.some((r) => r.id === activeReport.value.id)) {
    activeReport.value = null;
    stopPolling();
  }
}

async function resumeReport() {
  const reportId = activeReport.value?.id;
  if (!reportId || !canResumeMemo.value) return;
  generationError.value = null;
  resuming.value = true;
  try {
    const r = await api.resumeReport(reportId);
    activeReport.value = r;
    await loadCompanyReports();
    emit("reports-changed");
    startPolling();
  } catch (e) {
    generationError.value = requestErrorPayload(e);
    try {
      await loadCompanyReports();
    } catch {
      // Keep the original resume failure visible.
    }
  } finally {
    resuming.value = false;
  }
}

async function dismissFailedReport() {
  const reportId = activeReport.value?.id;
  if (!reportId) return;
  generationError.value = null;
  dismissing.value = true;
  try {
    await api.dismissReport(reportId);
    // The failure record is cleared — drop it from view entirely and land
    // on the company's normal (no-report) research state.
    activeReport.value = null;
    stopPolling();
    router.replace({
      name: "research",
      params: { companyId: props.companyId },
    });
    await loadCompanyReports();
    emit("reports-changed");
  } catch (e) {
    generationError.value = requestErrorPayload(e);
  } finally {
    dismissing.value = false;
  }
}

async function submitThread() {
  if (!newQuestion.value.trim()) return;
  submittingThread.value = true;
  submitThreadError.value = "";
  try {
    await api.addThread(props.companyId, {
      question: newQuestion.value.trim(),
      answer: newAnswer.value.trim(),
    });
    newQuestion.value = "";
    newAnswer.value = "";
    await loadThreads();
  } catch (e) {
    // Surface the failure — an unhandled rejection here left the user's
    // typed question apparently ignored with zero feedback.
    submitThreadError.value = e?.message || String(e);
  } finally {
    submittingThread.value = false;
  }
}

async function loadFromQuery() {
  const reportId = route.query.report;
  if (reportId) {
    try {
      const report = await api.getReport(reportId);
      // Stale-response guard: bail if the query changed while we awaited.
      if (route.query.report !== reportId) return;
      activeReport.value = report;
      activeTab.value = "memo";
      // Poll only genuinely in-flight runs. failed_* and
      // complete_with_warnings are terminal — polling them opened a
      // pointless SSE stream on every page load of a failed report.
      if (!isTerminalReportStatus(report.status)) startPolling();
    } catch (e) {
      if (route.query.report !== reportId) return;
      activeReport.value = null;
    }
  } else {
    stopPolling();
    await loadCompanyReports();
    const resumable = latestActionableMemoReport.value;
    if (!resumable?.id) {
      activeReport.value = null;
      return;
    }
    try {
      const report = await api.getReport(resumable.id);
      if (route.query.report) return; // navigated to a specific report meanwhile
      activeReport.value = report;
    } catch (e) {
      activeReport.value = null;
    }
  }
}

async function loadCompanyReports() {
  try {
    companyReports.value = await api.listCompanyReports(props.companyId);
  } catch (e) {
    companyReports.value = [];
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
  <div class="page-wide space-y-6">
    <header v-if="company" class="company-head">
      <div class="flex items-start gap-4">
        <Monogram :company="company" :size="56" tinted class="mt-1 max-sm:hidden" />
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <h1 ref="companyTitleEl" class="font-display text-title1 text-ink-primary">{{ company.name }}</h1>
            <CompanyFollowButton :company-id="company.id" size="md" />
            <template v-if="companyTicker">
              <RouterLink
                class="quote-chip focus-ring"
                :to="{ name: 'market-radar', query: { ticker: companyTicker } }"
                data-testid="company-live-quote"
              >
                <span class="text-caption1 font-semibold tracking-wide text-ink-secondary">{{ companyTicker }}</span>
                <span v-if="companyQuoteLabel" class="mono-data text-callout font-medium text-ink-primary">
                  {{ companyQuoteLabel }}
                </span>
                <span
                  v-if="companyQuoteChange != null"
                  class="price-pill"
                  :data-up="companyQuoteChange >= 0 ? 'true' : 'false'"
                >
                  {{ signedChange(companyQuoteChange) }}
                </span>
                <span v-else class="text-caption1 text-ink-subtle">{{ tr("tracking.quote_pending") }}</span>
              </RouterLink>
            </template>
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <span
              v-if="company.latest_funding?.round"
              class="chip bg-accent/10 text-accent-ink"
            >
              {{ fundingRoundLabel(company.latest_funding.round) }}
            </span>
            <span
              v-if="translatedCompanyField('industry') || translatedCompanyField('sector')"
              class="text-footnote text-ink-secondary"
            >
              {{ translatedCompanyField("industry") || translatedCompanyField("sector") }}
            </span>
            <a
              v-if="companyWebsiteHref"
              :href="companyWebsiteHref"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 rounded-[6px] text-footnote font-medium text-accent-ink hover:underline focus-ring"
            >
              {{ company.website.replace(/^https?:\/\//, "") }}
              <ExternalLink class="h-3 w-3" />
            </a>
          </div>
          <div class="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-caption1 text-ink-muted">
            <span v-if="company.founded_year">{{ tr("company.founded") }} {{ company.founded_year }}</span>
            <span v-if="company.founded_year && translatedCompanyField('hq')" aria-hidden="true">·</span>
            <span v-if="translatedCompanyField('hq')">{{ translatedCompanyField("hq") }}</span>
            <span v-if="translatedCompanyField('employee_band') && (company.founded_year || translatedCompanyField('hq'))" aria-hidden="true">·</span>
            <span v-if="translatedCompanyField('employee_band')">
              {{ translatedCompanyField("employee_band") }} {{ tr("company.employees") }}
            </span>
          </div>
          <div v-if="company.latest_funding" class="mono-data mt-1 text-caption1 text-ink-muted">
            {{ tr("company.last_round") }}
            {{
              isPendingValue(company.latest_funding.amount_usd)
                ? fundingRoundLabel(company.latest_funding.round)
                : fundingAmount(company.latest_funding.amount_usd)
            }}
            <template v-if="company.latest_funding.post_money_usd">
              · {{ tr("company.post_money") }} {{ fundingAmount(company.latest_funding.post_money_usd) }}
            </template>
            <template v-if="company.latest_funding.date">
              · {{ formatIsoDate(company.latest_funding.date) }}
            </template>
            <template v-if="company.total_funding_usd">
              · {{ tr("company.total_raised") }} {{ fundingAmount(company.total_funding_usd) }}
            </template>
          </div>
          <p v-if="refreshCompanyError" class="mt-2 text-caption1 text-danger">{{ refreshCompanyError }}</p>
        </div>
        <button
          type="button"
          class="btn-filled btn-sm shrink-0 inline-flex items-center gap-1.5 focus-ring shadow-sm"
          :aria-label="tr('memo.new_memo')"
          :title="`${tr('reports.custom_report_btn')} (⌘N)`"
          @click="openReportCustomizer(companyId)"
        >
          <AiMark class="h-3.5 w-3.5 shrink-0" />
          <span>{{ tr("memo.new_memo") }}</span>
        </button>
        <button
          type="button"
          @click="refreshCompanyRecord"
          :disabled="refreshingCompany"
          class="btn-bordered btn-sm shrink-0"
          :aria-label="refreshingCompany ? tr('company.refreshing') : tr('company.refresh')"
          :title="refreshingCompany ? tr('company.refreshing') : tr('company.refresh')"
        >
          <Loader2 v-if="refreshingCompany" class="h-3.5 w-3.5 animate-spin" />
          <RefreshCw v-else class="h-3.5 w-3.5" />
          <span class="hidden md:inline">{{ refreshingCompany ? tr("company.refreshing") : tr("company.refresh") }}</span>
        </button>
        <RouterLink
          :to="{ name: 'research-desk-company', params: { companyId } }"
          class="btn-bordered btn-sm shrink-0 inline-flex items-center gap-1.5 focus-ring"
          :title="tr('research_desk.open_desk')"
        >
          <Building2 class="h-3.5 w-3.5 text-accent" />
          <span class="hidden md:inline">{{ tr("research_desk.open_desk") }}</span>
        </RouterLink>
      </div>
      <!-- The positioning line frames the Overview; working tabs get the room back. -->
      <p v-if="activeTab === 'overview'" class="company-positioning">
        <template v-if="companyPositioning">
          <strong class="font-semibold text-ink-primary">{{ company.name }}</strong>
          {{ tr("research.positioning_is_a") }}
          <span class="position-highlight">{{ companyPositioning.category }}</span>
          {{ tr("research.positioning_for") }} {{ companyPositioning.customers }}
          {{ tr("research.positioning_who") }} {{ companyPositioning.need }},
          {{ tr("research.positioning_that") }}
          <span class="position-underline">{{ companyPositioning.benefit }}</span>.
          {{ tr("research.positioning_unlike") }} {{ companyPositioning.alternative }},
          {{ tr("research.positioning_it") }} {{ companyPositioning.differentiator }}.
        </template>
        <template v-else>
          <span class="position-highlight">{{ companyPositioningFallback.lead }}</span>
          {{ companyPositioningFallback.body }}
        </template>
      </p>
    </header>

    <div
      v-else-if="companyError"
      class="rounded-card bg-surface p-6 text-center"
    >
      <div class="font-display text-lg text-ink-primary">
        {{ companyErrorTitle }}
      </div>
      <p class="mt-1 text-sm text-ink-muted">
        {{ companyErrorBody }}
      </p>
      <button
        @click="router.push({ name: 'home' })"
        class="mt-3 text-sm text-accent hover:text-accent-hover focus-ring rounded"
      >
        {{ tr("research.back_to_search") }}
      </button>
    </div>
    <div v-else class="text-sm text-ink-muted">{{ tr("common.loading") }}</div>

    <!-- Flat company strip: Overview · Files · Report -->
    <div v-if="company" class="space-y-2">
      <div
        class="hairline-b flex max-w-full items-center gap-x-1 overflow-x-auto pb-px [scrollbar-width:none]"
        role="tablist"
      >
        <button
          v-for="tab in workspaceTabs.filter((item) => item.show)"
          :key="tab.id"
          type="button"
          @click="switchTab(tab.id)"
          :class="[ 'workspace-tab shrink-0 rounded-t-[8px] px-3 py-2.5 text-[13px] font-medium focus-ring sm:px-3.5 sm:text-callout', activeTab === tab.id ? 'text-ink-primary' : 'text-ink-muted hover:text-ink-primary', ]"
          role="tab"
          :aria-selected="activeTab === tab.id"
        >
          {{ tab.label }}
        </button>
      </div>
      <p v-if="isPublicCompany" class="text-caption1 text-ink-muted">
        {{ tr("research.public_no_reports") }}
      </p>
    </div>

    <CompanyDetail
      v-if="company && activeTab === 'overview'"
      :company="company"
      :tracking-updates="trackingUpdates"
      @refreshed="(c) => (company = c)"
    />

    <section
      v-if="company && activeTab === 'memo'"
      class="space-y-4"
    >
      <div class="flex flex-wrap items-center gap-2">
      <div
        class="segmented w-fit"
        role="tablist"
        :aria-label="tr('research.tab_memo')"
      >
        <button
          v-for="stage in memoStages"
          :key="stage.id"
          type="button"
          class="segmented-item focus-ring"
          :class="stage.enabled ? '' : 'segmented-item-muted'"
          :data-selected="memoStage === stage.id"
          :aria-selected="memoStage === stage.id"
          :aria-disabled="stage.enabled ? undefined : 'true'"
          :disabled="!stage.enabled"
          :title="stage.enabled ? undefined : tr('research.memo_stage_locked')"
          role="tab"
          @click="setMemoStage(stage.id)"
        >
          {{ stage.label }}
        </button>
      </div>
      <button
        type="button"
        class="btn-bordered btn-sm focus-ring !pl-1"
        @click="openAskInCopilot"
      >
        <WarrenMark :size="18" />
        {{ tr("research.ask_copilot_open") }}
      </button>
      <button
        type="button"
        class="btn-bordered btn-sm focus-ring inline-flex items-center gap-1.5"
        @click="openReportCustomizer(companyId)"
      >
        <SlidersHorizontal class="h-3.5 w-3.5 text-accent" />
        <span>{{ tr("research.memo_customize") }}</span>
      </button>
      </div>

      <div v-if="memoStage === 'studio'" class="space-y-4">
        <div class="rounded-card bg-surface shadow-card p-4 space-y-3">
          <div class="flex flex-wrap items-end gap-3">
            <label class="min-w-[12rem] flex-1">
              <div class="vogue-label mb-1.5">
                {{ tr("research.label_report_type") }}
              </div>
              <select v-model="reportType" class="field focus-ring">
                <option v-for="t in primaryReportTypes" :key="t" :value="t">
                  {{ reportTypeLabel(t) }}
                </option>
                <optgroup
                  v-if="moreReportTypes.length"
                  :label="tr('research.report_type_more')"
                >
                  <option v-for="t in moreReportTypes" :key="t" :value="t">
                    {{ reportTypeLabel(t) }}
                  </option>
                </optgroup>
              </select>
            </label>
            <label class="min-w-[10rem] flex-1">
              <div class="vogue-label mb-1.5">
                {{ tr("research.label_audience") }}
              </div>
              <select v-model="audience" class="field focus-ring">
                <option v-for="a in options.audiences" :key="a" :value="a">
                  {{ audienceLabel(a) }}
                </option>
              </select>
            </label>
            <div class="min-w-[12rem]">
              <div class="vogue-label mb-1.5">
                {{ tr("research.generation_mode") }}
              </div>
              <div
                class="segmented w-fit"
                role="radiogroup"
                :aria-label="tr('research.generation_mode')"
              >
                <button
                  type="button"
                  class="segmented-item focus-ring"
                  role="radio"
                  :data-selected="generationMode === 'one_click'"
                  :aria-checked="generationMode === 'one_click'"
                  @click="generationMode = 'one_click'"
                >
                  {{ tr("research.mode_one_click") }}
                </button>
                <button
                  type="button"
                  class="segmented-item focus-ring"
                  role="radio"
                  :data-selected="generationMode === 'studio_review'"
                  :aria-checked="generationMode === 'studio_review'"
                  @click="generationMode = 'studio_review'"
                >
                  {{ tr("research.mode_studio_review") }}
                </button>
              </div>
            </div>
            <div v-if="generationMode === 'one_click'" class="min-w-[10rem]">
              <div class="vogue-label mb-1.5">
                {{ tr("research.label_report_length") }}
              </div>
              <div
                class="segmented w-fit"
                role="radiogroup"
                :aria-label="tr('research.label_report_length')"
                :title="tr('research.report_length_compact_hint')"
              >
                <button
                  type="button"
                  class="segmented-item focus-ring"
                  role="radio"
                  :data-selected="reportMode === 'full'"
                  :aria-checked="reportMode === 'full'"
                  @click="reportMode = 'full'"
                >
                  {{ tr("research.report_length_full") }}
                </button>
                <button
                  type="button"
                  class="segmented-item focus-ring"
                  role="radio"
                  :data-selected="reportMode === 'compact'"
                  :aria-checked="reportMode === 'compact'"
                  @click="reportMode = 'compact'"
                >
                  {{ tr("research.report_length_compact") }}
                </button>
              </div>
            </div>
            <div v-if="generationMode === 'one_click'" class="min-w-[10rem]">
              <div class="vogue-label mb-1.5">
                {{ tr("research.label_quality") }}
              </div>
              <div
                class="segmented w-fit"
                role="radiogroup"
                :aria-label="tr('research.label_quality')"
                :title="tr('research.quality_hint')"
              >
                <button
                  type="button"
                  class="segmented-item focus-ring"
                  role="radio"
                  :data-selected="quality === 'best'"
                  :aria-checked="quality === 'best'"
                  @click="quality = 'best'"
                >
                  {{ tr("research.quality_best") }}
                </button>
                <button
                  type="button"
                  class="segmented-item focus-ring"
                  role="radio"
                  :data-selected="quality === 'balanced'"
                  :aria-checked="quality === 'balanced'"
                  @click="quality = 'balanced'"
                >
                  {{ tr("research.quality_balanced") }}
                </button>
                <button
                  type="button"
                  class="segmented-item focus-ring"
                  role="radio"
                  :data-selected="quality === 'economy'"
                  :aria-checked="quality === 'economy'"
                  @click="quality = 'economy'"
                >
                  {{ tr("research.quality_economy") }}
                </button>
              </div>
            </div>
          </div>
          <p class="text-xs text-ink-muted">
            {{
              generationMode === "one_click"
                ? tr("research.mode_one_click_hint")
                : studioReviewAvailable
                  ? tr("research.mode_studio_review_hint")
                  : tr("research.mode_buffett_one_click")
            }}
          </p>
          <div class="flex flex-wrap items-center gap-2">
            <button
              @click="runStudioCta"
              :disabled="generating || resuming || dismissing"
              class="btn-filled disabled:cursor-not-allowed focus-ring"
            >
              <Loader2 v-if="generating" class="h-4 w-4 animate-spin" />
              <AiMark v-else class="h-4 w-4" />
              <span>{{ studioCta.label }}</span>
            </button>
            <button
              v-if="!generating"
              type="button"
              class="btn-bordered focus-ring inline-flex items-center gap-1.5"
              :title="tr('customizer.title') + ' (⌘N)'"
              @click="openReportCustomizer(companyId)"
            >
              <SlidersHorizontal class="h-4 w-4 text-accent" />
              <span>{{ tr("research.memo_customize_run") }}</span>
            </button>
            <button
              v-if="awaitingStudio && !generating"
              type="button"
              class="btn-bordered btn-sm focus-ring"
              @click="startDeepInvestigate"
            >
              {{ tr("research.reinvestigate_button") }}
            </button>
            <button
              v-if="studioRegenerateAvailable && !generating"
              type="button"
              class="btn-bordered btn-sm focus-ring"
              @click="generateFromStudio"
            >
              {{ tr("research.regenerate_from_studio") }}
            </button>
            <span v-if="generating" class="text-xs text-ink-muted">
              {{ tr("research.progress_in_jobs") }}
            </span>
            <span v-else-if="awaitingStudio" class="text-xs text-ink-muted">
              {{
                tr("research.studio_cards_ready", {
                  date: studioInvestigationDate,
                })
              }}
            </span>
            <span v-else class="text-xs text-ink-muted">
              {{ reportTypeLabel(reportType) }} · {{ audienceLabel(audience) }}
            </span>
            <span
              v-if="activeReport?.trigger === 'tracking_auto_run'"
              class="rounded-full border border-accent/30 bg-accent-soft/50 px-2 py-0.5 text-[10px] font-semibold text-accent-ink"
              :title="activeReportAutoRunLabel"
            >
              {{ tr("research.auto_update_banner") }}<template v-if="activeReportAutoRunLabel"> · {{ activeReportAutoRunLabel }}</template>
            </span>
          </div>
          <div
            v-if="generationError"
            class="w-full rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-ink-primary"
          >
            <div class="font-semibold text-danger">
              {{ tr("research.generation_request_failed") }}
            </div>
            <p class="mt-1 text-ink-secondary">
              {{ tr("research.generation_error_body") }}
            </p>
          </div>
        </div>
        <div
          class="segmented w-fit"
          role="tablist"
          :aria-label="tr('research.memo_stage_studio')"
        >
          <button
            v-for="section in studioSections"
            :key="section.id"
            type="button"
            class="segmented-item focus-ring"
            :data-selected="studioSection === section.id"
            :aria-selected="studioSection === section.id"
            role="tab"
            @click="setStudioSection(section.id)"
          >
            {{ section.label }}
          </button>
        </div>
      </div>
    </section>

    <section
      v-if="activeReport && activeTab === 'memo' && (memoStage === 'studio' || memoStage === 'preview')"
      class="rounded-card bg-surface shadow-card p-6"
    >
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div class="vogue-label">
            {{ reportTypeLabel(activeReport.report_type) }} ·
            {{ audienceLabel(activeReport.audience) }}
            · {{ (activeReport.language || "en").toUpperCase() }}
          </div>
          <div class="font-display text-title3 text-ink-primary">
            {{ reportHeadline }}
          </div>
        </div>
        <span
          v-if="reportUserStatus === 'ready'"
          class="text-xs px-2 py-1 rounded bg-success-soft text-success-ink"
          >{{ reportUserStatusLabel }}</span
        >
        <span
          v-else-if="reportUserStatus === 'cards_ready'"
          class="text-xs px-2 py-1 rounded bg-accent-soft text-accent-ink"
          >{{ reportUserStatusLabel }}</span
        >
        <span
          v-else-if="reportUserStatus === 'needs_attention'"
          class="text-xs px-2 py-1 rounded bg-notice-soft text-notice-ink"
          >{{ reportUserStatusLabel }}</span
        >
        <span
          v-else-if="reportUserStatus === 'failed'"
          class="text-xs px-2 py-1 rounded bg-danger/10 text-danger"
          >{{ reportUserStatusLabel }}</span
        >
        <span
          v-else-if="reportUserStatus === 'running'"
          class="text-xs px-2 py-1 rounded bg-info-soft text-info-ink inline-flex items-center gap-1"
        >
          <Loader2 class="h-3 w-3 animate-spin" />
          {{ reportUserStatusLabel }}
        </span>
      </div>

      <p
        v-if="reportUserStatus === 'running'"
        class="mt-3 text-xs text-ink-muted"
      >
        {{ tr("research.progress_in_jobs") }}
      </p>

      <div
        v-if="pollConnectionLost"
        class="mt-3 flex items-center gap-3 rounded-lg border border-warning bg-warning-soft px-3 py-2 text-xs text-warning-ink"
      >
        <span>{{ tr("research.connection_lost") }}</span>
        <button
          type="button"
          class="font-semibold underline"
          @click="startPolling"
        >
          {{ tr("research.retry") }}
        </button>
      </div>

      <!-- Company type: classified in Phase 1 (registry `vertical` or the
           tool-free classifier); it steers research focus, the analysis
           lens and the scorecard weights for this run. -->
      <div
        v-if="isMemo && activeReport.company_type?.type"
        class="mt-4 rounded-lg border border-subtle bg-surface-muted p-4 text-sm text-ink-primary"
      >
        <span class="font-semibold">
          {{ tr("research.company_type_label") }}
        </span>
        <span class="ml-2">
          {{
            tr("research.company_type_" + activeReport.company_type.type)
          }}
        </span>
      </div>

      <!-- Company stage: the run's evidence-confirmed stage, pinned by
           the spine after Phase 2 research. Absent until the spine
           lands, so it never shows a registry guess. -->
      <div
        v-if="isMemo && activeReport.company_stage?.stage"
        class="mt-4 rounded-lg border border-subtle bg-surface-muted p-4 text-sm text-ink-primary"
      >
        <span class="font-semibold">
          {{ tr("research.company_stage_label") }}
        </span>
        <span class="ml-2">
          {{
            tr(
              "research.company_stage_" + activeReport.company_stage.stage,
            )
          }}
        </span>
      </div>

      <!-- Memo-specific affordances: downloads, partial analysis artifacts,
           and bilingual preview. Shown for complete runs and for failed
           runs when any generated output exists for QA. -->
      <div
        v-if="memoArtifactsVisible && (memoStage === 'preview' || reportIsFailed)"
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
            <span
              v-for="artifact in analysisArtifacts"
              :key="artifact.filename || artifact.label"
              class="inline-flex items-stretch"
            >
              <button
                type="button"
                @click="openArtifactViewer(artifact)"
                class="btn-bordered rounded-r-none focus-ring"
              >
                <FileText class="h-4 w-4" />
                <span>{{ artifact.label || artifact.filename }}</span>
              </button>
              <a
                :href="withApiToken(artifact.download_url || '#')"
                class="btn-bordered rounded-l-none border-l-0 !px-2.5 focus-ring"
                :aria-label="tr('research.download_artifact')"
              >
                <Download class="h-3.5 w-3.5 text-ink-muted" />
              </a>
            </span>
          </div>
        </div>
        <!-- Download + preview row: both .docx files (always available
             once complete) plus a PDF preview when one was rendered. -->
        <div class="flex flex-wrap items-center gap-3">
          <button
            v-if="Object.keys(activeReport.download_urls || {}).length"
            type="button"
            @click="openMemoDocViewer"
            class="btn-primary focus-ring"
          >
            <FileText class="h-4 w-4" />
            <span>{{ tr("research.view_in_document_viewer") }}</span>
          </button>
          <button
            v-if="activeReport.preview_urls?.en"
            type="button"
            @click="openMemoPreview('en')"
            class="btn-bordered focus-ring"
          >
            <Eye class="h-4 w-4" />
            <span>{{ tr("research.preview_pdf_en") }}</span>
          </button>
          <button
            v-if="activeReport.preview_urls?.zh"
            type="button"
            @click="openMemoPreview('zh')"
            class="btn-bordered focus-ring"
          >
            <Eye class="h-4 w-4" />
            <span>{{ tr("research.preview_pdf_zh") }}</span>
          </button>
          <button
            v-if="activeReport.preview_urls?.internal"
            type="button"
            @click="openMemoPreview('internal')"
            class="btn-bordered focus-ring"
          >
            <Eye class="h-4 w-4" />
            <span>{{ tr("research.preview_pdf_internal") }}</span>
          </button>
        </div>

        <!-- Language toggle for the preview body. -->
        <div
          v-if="activeReport.content_en || activeReport.content_zh"
          class="flex items-center gap-2 text-xs"
        >
          <span class="text-ink-muted">{{ tr("research.preview_label") }}</span>
          <button
            type="button"
            @click="previewLanguage = 'en'"
            :class="[ 'px-2 py-1 rounded', previewLanguage === 'en' ? 'bg-accent text-white' : 'bg-surface-muted text-ink-secondary hover:bg-surface', ]"
          >
            {{ tr("research.preview_en") }}
          </button>
          <button
            type="button"
            @click="previewLanguage = 'zh'"
            :class="[ 'px-2 py-1 rounded', previewLanguage === 'zh' ? 'bg-accent text-white' : 'bg-surface-muted text-ink-secondary hover:bg-surface', ]"
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

      <!-- Complete-with-warnings: the memo is delivered and usable, with
           the quality findings listed and Resume available to regenerate
           toward a clean memo. -->
      <div
        v-if="isMemo && reportHasWarnings && memoStage === 'studio'"
        class="mt-6 rounded-lg border border-notice/40 bg-notice-soft/40 p-4 text-sm text-ink-primary"
      >
        <div class="font-semibold text-warning-ink mb-1">
          {{ tr("research.complete_with_warnings_title") }}
        </div>
        <p class="text-ink-secondary">
          {{ tr("research.complete_with_warnings_body") }}
        </p>
        <ul
          v-if="Array.isArray(activeReport.quality_warnings) && activeReport.quality_warnings.length"
          class="mt-2 space-y-1 text-xs text-ink-secondary"
        >
          <li v-for="warning in activeReport.quality_warnings" :key="warning">
            <CopilotDropZone
              :company-id="companyId"
              surface="memo_report"
              tab="memo"
              :target-kind="TARGET_KINDS.MEMO_WARNING"
              :target-id="warning"
              block
              :selection="{
                warning,
                report_id: activeReport.id,
              }"
            >
              {{ warning }}
            </CopilotDropZone>
          </li>
        </ul>
        <ul v-if="gateFindings.length" class="mt-2 space-y-1 text-xs text-ink-muted">
          <li v-for="finding in gateFindings" :key="`warn-${finding.gateLabel}-${finding.code}-${finding.location}-${finding.snippet}`">
            <CopilotDropZone
              :company-id="companyId"
              surface="memo_report"
              tab="memo"
              :target-kind="TARGET_KINDS.GATE_FINDING"
              :target-id="`${finding.code}-${finding.location}`"
              block
              :selection="{
                code: finding.code,
                location: finding.location,
                snippet: finding.snippet,
                suggestion: finding.suggestion,
                gate_label: finding.gateLabel,
                report_id: activeReport?.id,
              }"
            >
              <span class="font-mono text-ink-secondary">{{ finding.code }}</span>
              <span v-if="finding.location"> · {{ finding.location }}</span>
              <span v-if="finding.snippet"> · {{ finding.snippet }}</span>
              <span v-if="finding.suggestion" class="mt-0.5 block text-ink-secondary">
                {{ tr("research.gate_finding_suggestion") }}: {{ finding.suggestion }}
              </span>
            </CopilotDropZone>
          </li>
        </ul>
        <button
          v-if="canResumeMemo"
          type="button"
          @click="resumeReport"
          :disabled="resuming || generating"
          class="btn-bordered mt-3 disabled:cursor-not-allowed focus-ring"
        >
          <Loader2 v-if="resuming" class="h-4 w-4 animate-spin" />
          <AiMark v-else class="h-4 w-4" />
          <span>{{ resuming ? tr("research.resuming_memo") : tr("research.resume_memo_improve") }}</span>
        </button>
      </div>

      <!-- Memo scope-fail: show the reason and the run folder for browsing. -->
      <!-- Generic failure banner for any failed_* memo run. -->
      <div
        v-if="
          isMemo &&
          memoStage === 'studio' &&
          String(activeReport.status || '').startsWith('failed') &&
          activeReport.status !== 'failed_scope_check' &&
          !activeReport.dismissed_at
        "
        class="mt-6 rounded-card border border-warning/40 bg-surface p-4 text-sm text-ink-primary"
      >
        <div class="font-semibold text-ink-primary mb-1">
          {{ reportFailureTitle }}
        </div>
        <p class="text-ink-secondary">{{ tr("research.failed_run_recovery_body") }}</p>
        <p v-if="reportFailedAtLabel" class="text-xs text-ink-muted">
          {{ tr("research.failed_run_at", { time: reportFailedAtLabel }) }}
        </p>
        <p v-if="activeReport.superseded_by" class="text-xs text-ink-muted">
          {{ tr("research.failed_run_superseded") }}
        </p>
        <p v-if="activeReport.stage" class="text-ink-secondary">
          {{ activeReport.stage }}
        </p>
        <p
          v-if="reportFailureDetail && reportFailureDetail !== activeReport.stage"
          class="mt-1 text-ink-secondary"
        >
          {{ reportFailureDetail }}
        </p>
        <div v-if="gateDiagnostics.length" class="mt-3">
          <div class="vogue-label">
            {{ tr("research.gate_diagnostics") }}
          </div>
          <ul class="mt-1 space-y-1 text-xs text-ink-secondary">
            <li v-for="diag in gateDiagnostics" :key="diag.label">
              {{ diag.label }}:
              {{ diag.p0Count }}
              {{ tr("research.gate_p0_findings") }}
              · {{ diag.findingCount }} {{ tr("research.gate_total_findings") }}
              <span v-if="diag.status">· {{ diag.status }}</span>
            </li>
          </ul>
        </div>
        <div v-if="rendererContractErrors.length" class="mt-3">
          <div class="vogue-label text-danger">
            {{ tr("research.renderer_contract_checks") }}
          </div>
          <ul class="mt-1 space-y-1 text-xs text-ink-secondary">
            <li v-for="err in rendererContractErrors" :key="err">
              {{ err }}
            </li>
          </ul>
        </div>
        <div v-if="rendererContractFiles.length" class="mt-3">
          <div class="vogue-label">
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
        </p>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <button
            v-if="canResumeMemo"
            type="button"
            @click="resumeReport"
            :disabled="resuming || generating || dismissing"
            class="btn-bordered disabled:cursor-not-allowed focus-ring"
          >
            <Loader2 v-if="resuming" class="h-4 w-4 animate-spin" />
            <AiMark v-else class="h-4 w-4" />
            <span>{{ resuming ? tr("research.resuming_memo") : tr("research.resume_memo") }}</span>
          </button>
          <button
            type="button"
            @click="runStudioCta"
            :disabled="generating || resuming || dismissing"
            class="btn-bordered text-ink-muted disabled:cursor-not-allowed focus-ring"
          >
            <AiMark class="h-4 w-4" />
            <span>{{ tr("research.redo_memo") }}</span>
          </button>
          <button
            type="button"
            @click="dismissFailedReport"
            :disabled="resuming || generating || dismissing"
            class="btn-bordered text-ink-muted disabled:cursor-not-allowed focus-ring"
          >
            <Loader2 v-if="dismissing" class="h-4 w-4 animate-spin" />
            <span>{{ dismissing ? tr("research.dismissing") : tr("research.dismiss_failed") }}</span>
          </button>
        </div>
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
        <p class="mt-2 text-xs text-warning-ink">{{ tr("research.scope_check_recovery") }}</p>
      </div>
    </section>

    <UnifiedDocumentsView
      v-if="company && activeTab === 'documents'"
      :company-id="companyId"
      :refresh-key="libraryRefresh"
      @open-report="openReportFromLibrary"
      @files-changed="handleDocumentsChanged"
    />

    <MemoStudioEditor
      v-if="canShowMemoStudio && activeTab === 'memo' && memoStage === 'studio' && studioSection === 'basic'"
      :company-id="companyId"
      :generate-available="awaitingStudio || studioRegenerateAvailable || studioGenerateRecoverable"
      :generating="generating"
      :refresh-key="activeReport?.studio_investigation?.seeded_revision_id || ''"
      @discuss="openMemoEditorDiscuss"
      @generate="generateFromStudio"
    />

    <section
      v-if="canShowMemoStudio && activeTab === 'memo' && memoStage === 'studio' && studioSection === 'advanced'"
      class="mt-6 rounded-card bg-surface shadow-card p-6"
    >
      <h2 class="font-display text-title3 text-ink-primary mb-1">
        {{ tr("research.advanced_tools") }}
      </h2>
      <div class="mt-4">
        <MemoAnalysisDashboard
          :company-id="companyId"
          :auto-start-investigation="true"
          @generate-memo="generate"
        />
      </div>
    </section>

    <section
      v-if="company && activeTab === 'memo' && memoStage === 'studio' && studioSection === 'notes'"
      class="rounded-card bg-surface shadow-card p-6"
    >
      <h2 class="font-display text-title3 text-ink-primary mb-1">
        {{ tr("research.ask_saved_notes") }}
      </h2>
      <p class="text-sm text-ink-muted mb-4">
        {{ tr("research.ask_copilot_body") }}
      </p>
        <form @submit.prevent="submitThread" class="mt-3 space-y-2">
          <input
            v-model="newQuestion"
            :placeholder="tr('research.ask_question_placeholder')"
            class="field focus-ring"
          />
          <textarea
            v-model="newAnswer"
            rows="2"
            :placeholder="tr('research.optional_notes_placeholder')"
            class="field resize-y focus-ring"
          ></textarea>
          <div class="flex items-center justify-end gap-3">
            <span v-if="submitThreadError" class="text-xs text-danger">
              {{ submitThreadError }}
            </span>
            <button
              type="submit"
              :disabled="!newQuestion.trim() || submittingThread"
              class="btn-bordered btn-sm focus-ring"
            >
              <Send class="h-3.5 w-3.5" />
              {{ tr("research.save_thread") }}
            </button>
          </div>
        </form>

        <div v-if="threads.length === 0" class="mt-3 text-sm text-ink-muted">
          {{ tr("research.no_threads") }}
        </div>
        <ul class="mt-3 space-y-3">
          <li
            v-for="thread in threads"
            :key="thread.id"
            class="border border-subtle rounded-lg p-3 bg-surface-muted"
          >
            <div class="text-sm font-medium text-ink-primary">{{ thread.question }}</div>
            <div
              v-if="thread.answer"
              class="mt-1 text-sm text-ink-secondary whitespace-pre-wrap"
            >
              {{ thread.answer }}
            </div>
            <div class="mt-1 text-xs text-ink-muted">{{ thread.created_at }}</div>
          </li>
        </ul>
    </section>

    <section
      v-if="company && activeTab === 'decisions'"
      class="rounded-card bg-surface shadow-card p-6"
    >
      <div class="mb-1 vogue-label">{{ tr("research.decision_record") }}</div>
      <p class="mb-4 text-sm text-ink-muted">
        {{ tr("research.decision_record_hint") }}
      </p>

      <form @submit.prevent="submitDecision" class="space-y-2">
        <div class="flex flex-wrap items-center gap-2">
          <select
            v-model="newDecisionVerdict"
            class="field w-auto focus-ring"
            :aria-label="tr('research.decision_verdict_label')"
            data-testid="decision-verdict"
          >
            <option value="invest">{{ tr("research.decision_verdict_invest") }}</option>
            <option value="pass">{{ tr("research.decision_verdict_pass") }}</option>
            <option value="watch">{{ tr("research.decision_verdict_watch") }}</option>
          </select>
          <input
            v-model="newDecisionDate"
            type="date"
            class="field w-auto focus-ring"
            :aria-label="tr('research.decision_date_label')"
            :title="tr('research.decision_date_hint')"
          />
          <select
            v-model="newDecisionReportId"
            class="field w-auto max-w-[16rem] focus-ring"
            :aria-label="tr('research.decision_report_label')"
          >
            <option value="">{{ tr("research.decision_report_none") }}</option>
            <option v-for="r in companyReports" :key="r.id" :value="r.id">
              {{ r.report_type }} · {{ (r.requested_at || "").slice(0, 10) }}
            </option>
          </select>
        </div>
        <textarea
          v-model="newDecisionExplanation"
          rows="2"
          :placeholder="tr('research.decision_explanation_placeholder')"
          class="field resize-y focus-ring"
          data-testid="decision-explanation"
        ></textarea>
        <div class="flex items-center justify-end gap-3">
          <span v-if="decisionSubmitError" class="text-xs text-danger">
            {{ tr("research.decision_add_failed") }}
          </span>
          <button
            type="submit"
            :disabled="!newDecisionExplanation.trim() || decisionSubmitting"
            class="btn-bordered btn-sm focus-ring"
          >
            {{ decisionSubmitting ? tr("research.decision_adding") : tr("research.decision_add") }}
          </button>
        </div>
      </form>

      <div
        v-if="!decisionRecords || decisionRecords.items?.length === 0"
        class="mt-4 rounded-subbox bg-fill-tertiary p-4 text-sm text-ink-muted"
      >
        {{ tr("research.decision_empty") }}
      </div>
      <ul v-else class="mt-4 space-y-3">
        <li
          v-for="row in decisionRecords.items"
          :key="row.id"
          class="rounded-row bg-fill-tertiary p-4"
        >
          <div class="flex flex-wrap items-center gap-2">
            <span :class="decisionChipClass(row.verdict)">
              {{ decisionVerdictLabel(row.verdict) }}
            </span>
            <span class="text-xs text-ink-muted">
              {{ tr("research.decision_decided_at", { date: (row.decided_at || "").slice(0, 10) }) }}
              <template v-if="row.created_by"> · {{ tr("research.decision_by", { name: row.created_by }) }}</template>
            </span>
            <span class="flex-1"></span>
            <button
              v-if="decisionLinkedReport(row)"
              type="button"
              class="text-xs font-medium text-accent hover:underline focus-ring rounded"
              @click="openReportFromLibrary(decisionLinkedReport(row))"
            >
              {{ tr("research.decision_view_report") }}
            </button>
            <button
              type="button"
              class="text-xs font-medium focus-ring rounded"
              :class="decisionDeleteArmId === row.id ? 'text-danger' : 'text-ink-muted hover:text-danger'"
              @click="removeDecision(row.id)"
            >
              {{ decisionDeleteArmId === row.id ? tr("research.decision_delete_confirm") : tr("research.decision_delete") }}
            </button>
          </div>
          <p class="mt-2 text-sm text-ink-secondary whitespace-pre-wrap">{{ row.explanation }}</p>
          <div v-if="row.retrospectives?.length" class="mt-3 space-y-2">
            <div class="text-caption1 font-medium text-ink-muted">
              {{ tr("research.decision_retro_heading") }}
            </div>
            <div
              v-for="retro in row.retrospectives"
              :key="retro.id"
              class="rounded-subbox bg-surface p-3"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span :class="retroChipClass(retro.verdict)">
                  {{ retroVerdictLabel(retro.verdict) }}
                </span>
                <span class="text-xs text-ink-muted">{{ (retro.assessed_at || "").slice(0, 10) }}</span>
              </div>
              <p v-if="retroRationale(retro)" class="mt-1 text-sm text-ink-secondary">
                {{ retroRationale(retro) }}
              </p>
            </div>
          </div>
        </li>
      </ul>
    </section>

    <section
      v-if="company && activeTab === 'news'"
      class="rounded-card bg-surface shadow-card p-6"
    >
      <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="vogue-label">{{ tr("research.tracked_updates") }}</div>
          <div class="mt-2 flex flex-wrap items-center gap-1.5">
            <span :class="impactChipClass('high')">{{ tr("research.impact_high") }} · {{ trackingUpdates?.counts?.high || 0 }}</span>
            <span :class="impactChipClass('medium')">{{ tr("research.impact_medium") }} · {{ trackingUpdates?.counts?.medium || 0 }}</span>
            <span :class="impactChipClass('low')">{{ tr("research.impact_low") }} · {{ trackingUpdates?.counts?.low || 0 }}</span>
          </div>
          <p v-if="trackingUpdates?.last_synced_at" class="mt-2 text-xs text-ink-muted">
            {{ tr("research.updates_last_synced") }}: {{ formatIsoDate(trackingUpdates.last_synced_at) }}
          </p>
          <p v-if="trackingScheduleLabel" class="mt-1 text-xs text-ink-muted">
            {{ trackingScheduleLabel }}
          </p>
          <AutoUpdateBar
            v-if="trackedAutoUpdate"
            class="mt-2"
            channel-id="tracked_news"
            :channel="trackedAutoUpdate"
            compact
            @updated="onTrackedCadenceSaved"
            @error="onTrackedCadenceError"
          />
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            role="switch"
            class="btn-bordered inline-flex items-center gap-2 focus-ring"
            :aria-checked="Boolean(trackingSettings?.auto_apply)"
            :disabled="trackingSettingsSaving || !trackingSettings"
            @click="toggleAutoApply"
          >
            {{
              tr(
                trackingSettings?.auto_apply
                  ? "research.updates_auto_apply_on"
                  : "research.updates_auto_apply_off",
              )
            }}
          </button>
          <button
            type="button"
            class="btn-bordered inline-flex items-center gap-2 focus-ring"
            :disabled="trackingSyncing"
            @click="syncTracking"
          >
            <Loader2 v-if="trackingSyncing" class="h-4 w-4 animate-spin" />
            {{ tr(trackingSyncing ? "research.updates_syncing" : "research.updates_sync") }}
          </button>
        </div>
      </div>
      <p v-if="!isFollowedCompany" class="mb-3 text-sm text-ink-muted">
        {{ tr("research.updates_follow_hint") }}
      </p>
      <div v-if="trackingSyncError" class="mb-3 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
        {{ tr("research.updates_sync_failed") }}
      </div>
      <div v-if="executeNotice" class="mb-3 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-ink-secondary">
        <div class="flex flex-wrap items-center gap-3">
          <span>{{ executeNotice }}</span>
          <button
            v-if="pendingReviewRunId"
            type="button"
            class="btn-bordered btn-sm focus-ring"
            :disabled="Boolean(executingAutoRunId)"
            @click="confirmReviewedAndRun"
          >
            {{ tr("research.updates_confirm_reviewed") }}
          </button>
        </div>
      </div>
      <div
        v-if="!trackingUpdates?.auto_runs?.length && !trackingUpdates?.items?.length"
        class="rounded-subbox bg-fill-tertiary p-4 text-sm text-ink-muted"
      >
        {{ tr("research.updates_empty") }}
      </div>
      <ul v-else-if="trackingUpdates?.auto_runs?.length" class="space-y-3">
        <li
          v-for="run in trackingUpdates.auto_runs"
          :key="run.id"
          class="rounded-row bg-fill-tertiary p-4"
        >
          <div class="flex flex-wrap items-center gap-2">
            <span :class="autoRunStatusChipClass(run.status)">
              {{ autoRunStatusLabel(run) }}
            </span>
            <span class="rounded-pill bg-surface px-2 py-0.5 text-caption1 font-semibold text-ink-muted">
              {{ tr(run.action === "full_report" ? "research.action_full_report" : "research.action_investigate") }}
            </span>
            <div class="ml-auto flex items-center gap-2">
              <button
                v-if="run.status === 'recommended'"
                type="button"
                class="btn-bordered inline-flex items-center gap-2 focus-ring"
                :disabled="Boolean(executingAutoRunId)"
                @click="runAutoRun(run)"
              >
                <Loader2 v-if="executingAutoRunId === run.id" class="h-4 w-4 animate-spin" />
                {{ tr("research.updates_run_now") }}
              </button>
              <button
                v-if="run.job_ref?.report_id"
                type="button"
                class="text-xs font-semibold text-accent-ink hover:underline focus-ring"
                @click="openReportFromLibrary({ id: run.job_ref.report_id })"
              >
                {{ tr("research.updates_view_report") }}
              </button>
            </div>
          </div>
          <p class="mt-2 text-sm text-ink-secondary">{{ run.label }}</p>
        </li>
      </ul>
    </section>

    <section
      v-if="company && activeTab === 'news'"
      class="rounded-card bg-surface shadow-card p-6"
    >
      <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="flex items-center gap-2">
            <div class="vogue-label">{{ tr("research.tab_news") }}</div>
            <span class="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent-soft px-2 py-0.5 text-[10px] font-bold text-accent-ink">
              <span class="live-pulse h-1.5 w-1.5 rounded-full bg-accent"></span>
              {{ tr("research.news_live") }}
            </span>
          </div>
          <h2 class="mt-1 font-display text-title2 text-ink-primary">
            {{ tr("research.news_feed_title") }}
          </h2>
          <p class="mt-1 text-sm text-ink-muted">
            {{ tr("research.news_feed_subtitle") }}
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="btn-bordered focus-ring"
            :disabled="newsSweeping"
            data-testid="news-sweep"
            @click="sweepNewsFeed"
          >
            <Loader2 v-if="newsSweeping" class="mr-1.5 inline h-3.5 w-3.5 animate-spin" />
            {{ newsSweeping ? tr("research.news_sweeping") : tr("research.news_sweep") }}
          </button>
          <button
            type="button"
            class="btn-bordered focus-ring"
            @click="$emit('open-copilot')"
          >
            {{ tr("research.news_submit_link") }}
          </button>
        </div>
      </div>

      <p
        v-if="newsSweep"
        class="mb-3 text-xs"
        :class="newsSweep.error ? 'text-danger' : 'text-ink-muted'"
        data-testid="news-sweep-status"
      >
        <template v-if="newsSweep.error">
          {{ tr("research.news_sweep_failed", { reason: newsSweep.error }) }}
        </template>
        <template v-else-if="newsSweep.added">
          {{ tr("research.news_sweep_added", { count: newsSweep.added }) }}
          <span v-if="newsSweep.sources?.length">
            · {{ tr("research.news_sweep_sources", { count: newsSweep.sources.length }) }}
          </span>
        </template>
        <template v-else>{{ tr("research.news_sweep_none") }}</template>
      </p>

      <form class="mb-4 flex flex-col gap-3" @submit.prevent="loadNewsFeed">
        <input
          v-model="newsSearch"
          type="search"
          :placeholder="tr('research.news_search_placeholder')"
          class="field focus-ring"
        />
        <div class="flex flex-wrap items-center gap-2" role="group" :aria-label="tr('research.news_filter_label')">
          <button
            v-for="filter in NEWS_FILTERS"
            :key="filter.value || 'all'"
            type="button"
            @click="selectNewsCategory(filter.value)"
            :class="[ 'rounded-full border px-3 py-1.5 text-xs font-semibold focus-ring', newsCategory === filter.value ? 'border-ink-primary bg-ink-primary text-white' : 'border-subtle bg-surface text-ink-secondary hover:bg-surface-muted', ]"
            :aria-pressed="newsCategory === filter.value"
          >
            {{ tr(filter.labelKey) }}
          </button>
          <button type="submit" class="ml-auto rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs font-semibold text-ink-secondary hover:bg-surface-muted focus-ring">
            {{ tr("research.news_search") }}
          </button>
        </div>
      </form>

      <div v-if="newsLoading" class="flex items-center gap-2 text-sm text-ink-muted">
        <Loader2 class="h-4 w-4 animate-spin" />
        {{ tr("research.news_loading") }}
      </div>
      <div v-else-if="newsError" class="rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
        {{ tr("research.news_load_error") }}
      </div>
      <div v-else-if="companyNews.length === 0" class="rounded-subbox bg-fill-tertiary p-4 text-sm text-ink-muted">
        {{ newsFeed.empty_state || tr("research.news_empty") }}
      </div>
      <ul v-else class="space-y-3">
        <li
          v-for="item in companyNews"
          :key="item.id || item.headline || item.title"
          class="rounded-row bg-fill-tertiary p-4"
        >
          <div class="flex items-start gap-3">
            <span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-accent"></span>
            <div class="min-w-0 flex-1">
              <div class="mono-data text-[11px] text-footnote font-semibold text-ink-muted">{{ newsMeta(item) }}</div>
              <div class="mt-1 flex flex-wrap items-center gap-2">
                <span class="text-sm font-semibold text-ink-primary">{{ item.title || item.headline }}</span>
                <span
                  v-if="feedItemImpact(item)"
                  :class="impactChipClass(feedItemImpact(item).impact)"
                  :title="feedItemImpact(item).impact === 'low' ? tr('research.action_save_only') : ''"
                >
                  {{ impactLabel(feedItemImpact(item).impact) }}
                </span>
              </div>
              <p v-if="item.summary" class="mt-1 text-sm leading-relaxed text-ink-secondary">{{ item.summary }}</p>
            </div>
            <a
              v-if="item.url || item.archive_url"
              :href="item.url || item.archive_url"
              target="_blank"
              rel="noopener"
              class="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-subtle text-ink-muted hover:border-accent hover:text-accent-ink focus-ring"
              :aria-label="tr('research.news_open_source')"
              :title="tr('research.news_open_source')"
            >
              <ExternalLink class="h-4 w-4" />
            </a>
          </div>
          <div v-if="item.tags?.length" class="mt-3 flex flex-wrap gap-1.5">
            <span
              v-for="tag in item.tags"
              :key="`${item.id}-${tag}`"
              class="rounded-full bg-surface px-2 py-0.5 text-caption1 font-semibold text-ink-muted"
            >
              {{ tag }}
            </span>
          </div>
        </li>
      </ul>
    </section>

    <section
      v-if="company && activeTab === 'overview'"
      class="space-y-5"
    >
      <div class="rounded-card bg-surface p-6 shadow-card">
        <div class="vogue-label">{{ tr("research.tab_industry") }}</div>
        <h2 class="mt-1 font-display text-title2 text-ink-primary">
          {{ industryView?.title || translatedCompanyField("industry") || translatedCompanyField("sector") || tr("research.industry_context") }}
        </h2>
        <p class="mt-1 max-w-3xl text-sm text-ink-muted">
          {{ industryView?.summary || tr("research.industry_summary") }}
        </p>
        <div v-if="industryLoading" class="mt-4 flex items-center gap-2 text-sm text-ink-muted">
          <Loader2 class="h-4 w-4 animate-spin" />
          {{ tr("research.industry_loading") }}
        </div>
        <div v-if="industryError" class="mt-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
          {{ tr("research.industry_load_error") }}
        </div>
        <div
          class="mt-5 grid overflow-hidden rounded-card border border-subtle sm:grid-cols-2 lg:grid-cols-4"
        >
          <div
            v-for="metric in industryMetricSlots"
            :key="metric.label"
            class="border-b border-subtle bg-surface p-4 last:border-b-0 sm:border-r sm:[&:nth-child(2)]:border-r-0 lg:border-b-0 lg:[&:nth-child(2)]:border-r lg:last:border-r-0"
          >
            <div class="vogue-label text-[10px]">{{ metric.label }}</div>
            <div class="mono-data mt-2 font-bold" :class="isPendingValue(metric.value) ? 'text-xl text-ink-subtle' : 'text-2xl text-ink-primary'">
              {{ isPendingValue(metric.value) ? "—" : formatMetricValue(metric.label, metric.value) }}
            </div>
            <div class="mt-1 text-[11px] text-ink-muted">
              {{ metric.source_class || tr("research.source_pending") }}
              <span v-if="metric.as_of">· {{ formatIsoDate(metric.as_of) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="rounded-card bg-surface p-6 shadow-card">
        <div class="vogue-label">{{ tr("research.industry_expert_opinions") }}</div>
        <div v-if="expertOpinions.length === 0" class="mt-3 text-sm text-ink-muted">
          {{ tr("research.industry_expert_empty") }}
        </div>
        <div v-else class="mt-4 divide-y divide-subtle rounded-card border border-subtle">
          <article
            v-for="opinion in expertOpinions"
            :key="`${opinion.speaker}-${opinion.date}`"
            class="flex gap-3 bg-surface p-4"
          >
            <div class="mono-data grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold text-accent-ink">{{ monogram(opinion.speaker) }}</div>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-sm font-semibold text-ink-primary">{{ opinion.speaker }}</span>
                <span class="text-xs text-ink-muted">{{ opinion.affiliation }}</span>
                <span class="rounded-full px-2 py-0.5 text-[10px] font-bold" :class="{ 'bg-accent-soft text-accent-ink': opinion.stance === 'Bullish', 'bg-danger-soft text-danger-ink': opinion.stance === 'Cautious', 'bg-surface-muted text-ink-muted': opinion.stance !== 'Bullish' && opinion.stance !== 'Cautious', }">{{ opinion.stance || tr("research.industry_neutral") }}</span>
                <span class="mono-data text-xs text-ink-muted">{{ formatIsoDate(opinion.date, "") }}</span>
              </div>
              <p class="mt-2 text-sm italic leading-relaxed text-ink-secondary">“{{ opinion.summary || opinion.quote }}”</p>
              <div class="mt-2 text-[11px] text-ink-muted">
                {{ opinion.source_class || tr("research.source_pending") }}
                <span v-if="opinion.source_refs?.[0]?.title">· {{ opinion.source_refs[0].title }}</span>
              </div>
            </div>
          </article>
        </div>
      </div>

      <div class="grid gap-5 lg:grid-cols-2">
        <div class="rounded-card bg-surface p-6 shadow-card">
          <div class="vogue-label">{{ tr("research.industry_public_comps") }}</div>
          <div v-if="publicComps.length === 0" class="mt-3 text-sm text-ink-muted">
            {{ tr("research.industry_comps_empty") }}
          </div>
          <div v-else class="mt-4 space-y-3">
            <article
              v-for="comp in publicComps"
              :key="comp.id || comp.ticker"
              class="rounded-subbox bg-fill-tertiary p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="font-semibold text-ink-primary">{{ comp.name }}</div>
                  <div class="mono-data mt-0.5 text-xs text-ink-muted">
                    {{ comp.exchange ? `${comp.exchange}:` : "" }}{{ comp.ticker || "N/A" }}
                  </div>
                </div>
                <span
                  class="mono-data rounded-full px-2 py-0.5 text-xs font-semibold"
                  :class="String(comp.change || '').startsWith('-') ? 'bg-danger-soft text-danger-ink' : 'bg-accent-soft text-accent-ink'"
                >
                  {{ comp.change || "flat" }}
                </span>
              </div>
              <p class="mt-2 text-sm leading-relaxed text-ink-secondary">
                {{ comp.note || tr("research.industry_comp_pending") }}
              </p>
              <div class="mt-3 flex h-8 items-end gap-1" aria-hidden="true">
                <span
                  v-for="(point, index) in comp.sparkline || []"
                  :key="`${comp.id}-${index}`"
                  class="w-2 rounded-t bg-accent/70"
                  :style="{ height: `${Math.max(8, Number(point || 1) * 4)}px` }"
                ></span>
              </div>
              <div class="mt-2 text-[11px] text-ink-muted">
                {{ comp.source_class || tr("research.source_pending") }}
              </div>
            </article>
          </div>
        </div>

        <div class="rounded-card bg-surface p-6 shadow-card">
          <div class="vogue-label">{{ tr("research.industry_sector_signals") }}</div>
          <div v-if="sectorSignals.length === 0" class="mt-3 text-sm text-ink-muted">
            {{ tr("research.industry_signals_empty") }}
          </div>
          <div v-else class="mt-4 space-y-3">
            <article
              v-for="signal in sectorSignals"
              :key="signal.id || signal.signal"
              class="rounded-subbox bg-fill-tertiary p-4"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full bg-warning-soft px-2 py-0.5 text-caption1 font-semibold text-warning-ink">
                  {{ signal.category || tr("research.industry_sector") }}
                </span>
                <span class="text-[11px] text-ink-muted">
                  {{ signal.source_class || tr("research.industry_market_data") }}
                </span>
              </div>
              <div class="mt-2 text-sm font-semibold text-ink-primary">
                {{ signal.signal }}
              </div>
              <p class="mt-1 text-sm leading-relaxed text-ink-secondary">
                {{ signal.implication }}
              </p>
            </article>
          </div>
        </div>
      </div>
    </section>

    <FilePreviewModal
      :file="previewFile"
      :preview-url="previewPdfUrl"
      :download-url="previewDocxUrl"
      :report-id="activeReport?.id || null"
      :previewable-kinds="['pdf']"
      @close="closeMemoPreview"
    />

    <DocumentViewerDrawer
      v-if="docViewer"
      :title="docViewer.title"
      :sources="docViewer.sources"
      @close="closeDocViewer"
    />
  </div>
</template>
