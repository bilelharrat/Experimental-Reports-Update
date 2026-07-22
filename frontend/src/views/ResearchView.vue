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
  RefreshCw,
  Send,
  Sparkles,
} from "lucide-vue-next";
import { api, withApiToken } from "../api.js";
import {
  formatCompactNumber,
  formatIsoDate,
  formatMetricValue,
  humanizeStatus,
  isPendingValue,
} from "../formatters.js";
import { useT } from "../i18n.js";
import { POLL_MAX_FAILURES, pollDelayMs } from "../pollBackoff.js";
import { appLanguage } from "../state.js";
import CompanyDetail from "../components/CompanyDetail.vue";
import FilePreviewModal from "../components/FilePreviewModal.vue";
import MemoAnalysisDashboard from "../components/MemoAnalysisDashboard.vue";
import MemoStudioEditor from "../components/MemoStudioEditor.vue";
import UnifiedDocumentsView from "../components/UnifiedDocumentsView.vue";

const tr = useT();

// Backend returns canonical option strings (e.g. "Investment Memo (Late-Stage)",
// "Internal"). Map them to localized display labels here; unknown values fall
// through to the raw string so new server-side options keep working.
const REPORT_TYPE_ZH = {
  "Investment Memo (Late-Stage)": "投资备忘录（Late-Stage / Pre-IPO）",
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
const MEMO_REPORT_TYPE = "Investment Memo (Late-Stage)";
function reportTypeLabel(val) {
  if (appLanguage.value === "zh") return REPORT_TYPE_ZH[val] || val;
  return val;
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

const company = ref(null);
const companyError = ref(null);
const options = ref({ report_types: [], audiences: [], languages: [] });
const newsFeed = ref({ rows: [], filters: { categories: [], tags: [] }, empty_state: "" });
const newsLoading = ref(false);
const newsError = ref("");
const newsCategory = ref("");
const newsSearch = ref("");
const industryView = ref(null);
const industryLoading = ref(false);
const industryError = ref("");
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

// Default to the late-stage investment memo — the only fully-wired
// pipeline. Other types still route through the legacy stub generator.
const reportType = ref(MEMO_REPORT_TYPE);
const audience = ref("Internal");

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
const latestResumableMemoReport = computed(() => {
  const reports = Array.isArray(companyReports.value) ? companyReports.value : [];
  return [...reports]
    .filter(
      (report) =>
        report?.kind === "investment_memo_latestage" &&
        report?.resume_available &&
        (String(report?.status || "").startsWith("failed") ||
          String(report?.status || "") === "complete_with_warnings"),
    )
    .sort((a, b) =>
      String(b.updated_at || b.created_at || "").localeCompare(
        String(a.updated_at || a.created_at || ""),
      ),
    )[0] || null;
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
  return r.stage || humanizeStatus(r.status) || "";
});
const displayedReportProgress = computed(() =>
  reportIsFailed.value ? 0 : Math.max(0, Math.min(100, Number(activeReport.value?.progress || 0))),
);
const analysisArtifacts = computed(() => {
  const artifacts = activeReport.value?.analysis_artifacts;
  return Array.isArray(artifacts) ? artifacts : [];
});
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
  return items;
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

const libraryRefresh = ref(0);

const TAB_IDS = ["overview", "documents", "memo", "news", "industry"];
function normalizeTabName(raw) {
  if (raw === "analysis") return "memo";
  if (raw === "console") {
    emit("open-copilot");
    return "overview";
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
  router.replace({
    name: "research",
    params: { companyId: props.companyId },
    query: { ...route.query, tab: nextTab === "overview" ? undefined : nextTab },
  });
}
watch(
  () => [route.query.tab, route.query.report],
  ([tab]) => {
    activeTab.value = normalizeTabName(tab);
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

const workspaceTabs = computed(() => [
  { id: "overview", label: tr("research.tab_overview"), show: true },
  { id: "documents", label: tr("research.tab_documents"), show: true },
  { id: "memo", label: tr("research.tab_memo"), show: canShowMemoStudio.value },
  { id: "news", label: tr("research.tab_news"), show: true },
  { id: "industry", label: tr("research.tab_industry"), show: true },
]);

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
// A ticker so elapsed/ETA labels keep moving even between poll responses.
const nowTick = ref(Date.now());
let nowTickId = null;

// Memo generation legitimately runs ~19–34 minutes end-to-end; surface
// elapsed + a rough ETA so an in-flight run is distinguishable from a hang.
const MEMO_TYPICAL_MAX_MIN = 34;

const reportInProgress = computed(() => {
  const status = String(activeReport.value?.status || "");
  return (
    Boolean(activeReport.value) &&
    status !== "complete" &&
    status !== "complete_with_warnings" &&
    !status.startsWith("failed")
  );
});
const reportElapsedMin = computed(() => {
  const created = activeReport.value?.created_at;
  if (!created) return null;
  const started = Date.parse(created);
  if (Number.isNaN(started)) return null;
  return Math.max(0, Math.round((nowTick.value - started) / 60000));
});
const reportEtaMin = computed(() => {
  const elapsed = reportElapsedMin.value;
  if (elapsed == null) return null;
  return Math.max(1, MEMO_TYPICAL_MAX_MIN - elapsed);
});

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
  try {
    company.value = await api.getCompany(props.companyId);
    await Promise.allSettled([loadNewsFeed(), loadIndustryView()]);
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
      status.startsWith("failed")
    ) {
      stopPolling();
      await loadCompanyReports();
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
  if (!nowTickId) nowTickId = setInterval(() => { nowTick.value = Date.now(); }, 15000);
}
function stopPolling() {
  pollActive = false;
  closeMemoStream();
  if (pollId) clearTimeout(pollId);
  pollId = null;
  if (nowTickId) clearInterval(nowTickId);
  nowTickId = null;
}

async function generate(analysisSessionId = null, options = {}) {
  const memoAnalysisSessionId =
    typeof analysisSessionId === "string" ? analysisSessionId : null;
  const forceFresh = Boolean(options?.forceFresh);
  if (canResumeMemo.value && !forceFresh) {
    await resumeReport();
    return;
  }
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

function openMemoEditorDiscuss() {
  emit("open-copilot");
}

function handleDocumentsChanged() {
  libraryRefresh.value += 1;
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
      activeTab.value = "memo";
      if (activeReport.value.status !== "complete") startPolling();
    } catch (e) {
      activeReport.value = null;
    }
  } else {
    stopPolling();
    await loadCompanyReports();
    const resumable = latestResumableMemoReport.value;
    if (!resumable?.id) {
      activeReport.value = null;
      return;
    }
    try {
      activeReport.value = await api.getReport(resumable.id);
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
  <div class="w-full px-8 py-10 space-y-8">
    <div>
      <button
        @click="router.push({ name: 'home' })"
        class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-sm text-ink-muted hover:bg-surface-muted hover:text-ink-primary focus-ring"
      >
        <ArrowLeft class="h-4 w-4" /> {{ tr("research.back_to_search") }}
      </button>
    </div>

    <header
      v-if="company"
      class="rounded-card border border-subtle bg-surface p-6 shadow-card"
    >
      <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div class="flex min-w-0 items-start gap-4">
          <div
            class="mono-data grid h-16 w-16 shrink-0 place-items-center rounded-glass bg-accent-soft text-xl font-bold text-accent-ink ring-1 ring-subtle"
          >
            {{ monogram(company.name) }}
          </div>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="font-display text-3xl font-bold text-ink-primary">
                {{ company.name }}
              </h1>
              <span
                v-if="company.latest_funding?.round"
                class="rounded-chip bg-surface-muted px-2 py-1 text-xs font-semibold text-ink-secondary"
              >
                {{ fundingRoundLabel(company.latest_funding.round) }}
              </span>
              <span
                v-if="translatedCompanyField('industry') || translatedCompanyField('sector')"
                class="rounded-chip bg-accent-soft px-2 py-1 text-xs font-semibold text-accent-ink"
              >
                {{ translatedCompanyField("industry") || translatedCompanyField("sector") }}
              </span>
              <a
                v-if="companyWebsiteHref"
                :href="companyWebsiteHref"
                target="_blank"
                rel="noopener"
                class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold text-accent-ink hover:bg-accent-soft hover:text-ink-primary focus-ring"
              >
                <ExternalLink class="h-3.5 w-3.5" />
                {{ company.website.replace(/^https?:\/\//, "") }}
              </a>
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-muted">
              <span v-if="company.founded_year">{{ tr("company.founded") }} {{ company.founded_year }}</span>
              <span v-if="translatedCompanyField('hq')">{{ translatedCompanyField("hq") }}</span>
              <span v-if="translatedCompanyField('employee_band')">
                {{ translatedCompanyField("employee_band") }} {{ tr("company.employees") }}
              </span>
            </div>
            <div v-if="company.latest_funding" class="mono-data mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
              <span class="font-semibold text-ink-secondary">{{ tr("company.last_round") }}</span>
              <span class="font-bold text-ink-primary">
                {{
                  isPendingValue(company.latest_funding.amount_usd)
                    ? fundingRoundLabel(company.latest_funding.round)
                    : fundingAmount(company.latest_funding.amount_usd)
                }}
              </span>
              <span v-if="company.latest_funding.post_money_usd">
                · {{ tr("company.post_money") }} {{ fundingAmount(company.latest_funding.post_money_usd) }}
              </span>
              <span v-if="company.latest_funding.date">· {{ formatIsoDate(company.latest_funding.date) }}</span>
              <span v-if="company.total_funding_usd">
                · {{ tr("company.total_raised") }} {{ fundingAmount(company.total_funding_usd) }}
              </span>
            </div>
            <p v-if="refreshCompanyError" class="mt-2 text-xs text-danger">{{ refreshCompanyError }}</p>
          </div>
        </div>
        <button
          type="button"
          @click="refreshCompanyRecord"
          :disabled="refreshingCompany"
          class="pill-button shrink-0 border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring"
        >
          <Loader2 v-if="refreshingCompany" class="h-4 w-4 animate-spin" />
          <RefreshCw v-else class="h-4 w-4" />
          {{ refreshingCompany ? tr("company.refreshing") : tr("company.refresh") }}
        </button>
      </div>
      <p class="mt-5 border-t border-subtle pt-5 text-base leading-7 text-ink-primary">
        <template v-if="companyPositioning">
          <strong>{{ company.name }}</strong>
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
      class="rounded-card border border-subtle bg-surface p-6 text-center"
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

    <!-- PRD workspace tabs. Legacy tab=analysis maps to Memo Studio. -->
    <div
      v-if="company"
      class="flex max-w-full flex-wrap items-center gap-x-1 gap-y-2 border-b border-subtle pb-px"
    >
      <button
        v-for="tab in workspaceTabs.filter((item) => item.show)"
        :key="tab.id"
        @click="switchTab(tab.id)"
        :class="[
          'workspace-tab px-3 py-2 text-xs font-medium focus-ring sm:px-4 sm:text-sm',
          activeTab === tab.id
            ? 'text-ink-primary'
            : 'text-ink-muted hover:text-ink-primary',
        ]"
        role="tab"
        :aria-selected="activeTab === tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <CompanyDetail
      v-if="company && activeTab === 'overview'"
      :company="company"
      @refreshed="(c) => (company = c)"
    />

    <section
      v-if="company && activeTab === 'memo'"
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
          @click="generate()"
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
      <div
        v-if="generationError"
        class="mt-4 rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-ink-primary"
      >
        <div class="font-semibold text-danger">
          {{ tr("research.generation_request_failed") }}
        </div>
        <p class="mt-1 text-ink-secondary">
          {{ tr("research.generation_error_body") }}
        </p>
      </div>
    </section>

    <section
      v-if="activeReport && activeTab === 'memo'"
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
          v-else-if="activeReport.status === 'complete_with_warnings'"
          class="text-xs px-2 py-1 rounded bg-warning-soft text-warning-ink"
          >{{ tr("research.status_complete_warnings") }}</span
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
          {{ displayedReportProgress }}%
        </span>
      </div>

      <div class="mt-4 h-2 w-full rounded-full bg-surface-muted overflow-hidden">
        <div
          class="h-full bg-accent transition-all"
          :style="{ width: displayedReportProgress + '%' }"
        ></div>
      </div>

      <div
        v-if="isMemo && reportInProgress"
        class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted"
      >
        <span v-if="activeReport.stage" class="text-ink-secondary font-medium">
          {{ activeReport.stage }}
        </span>
        <span v-if="reportElapsedMin != null">
          {{ tr("research.progress_elapsed", { minutes: reportElapsedMin }) }}
        </span>
        <span v-if="reportEtaMin != null">
          {{ tr("research.progress_eta", { minutes: reportEtaMin }) }}
        </span>
        <span>{{ tr("research.progress_safe_to_close") }}</span>
      </div>

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
        v-if="!reportIsFailed && activeReport.stages && activeReport.stages.length"
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

      <!-- Complete-with-warnings: the memo is delivered and usable, with
           the quality findings listed and Resume available to regenerate
           toward a clean memo. -->
      <div
        v-if="isMemo && reportHasWarnings"
        class="mt-6 rounded-lg border border-warning/40 bg-warning-soft/40 p-4 text-sm text-ink-primary"
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
            {{ warning }}
          </li>
        </ul>
        <ul v-if="gateFindings.length" class="mt-2 space-y-1 text-xs text-ink-muted">
          <li v-for="finding in gateFindings" :key="`warn-${finding.gateLabel}-${finding.code}-${finding.location}-${finding.snippet}`">
            <span class="font-mono text-ink-secondary">{{ finding.code }}</span>
            <span v-if="finding.location"> · {{ finding.location }}</span>
            <span v-if="finding.snippet"> · {{ finding.snippet }}</span>
          </li>
        </ul>
        <button
          v-if="canResumeMemo"
          type="button"
          @click="resumeReport"
          :disabled="resuming || generating"
          class="mt-3 inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 disabled:cursor-not-allowed focus-ring"
        >
          <Loader2 v-if="resuming" class="h-4 w-4 animate-spin" />
          <Sparkles v-else class="h-4 w-4" />
          <span>{{ resuming ? tr("research.resuming_memo") : tr("research.resume_memo_improve") }}</span>
        </button>
      </div>

      <!-- Memo scope-fail: show the reason and the run folder for browsing. -->
      <!-- Generic failure banner for any failed_* memo run. -->
      <div
        v-if="
          isMemo &&
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
          <div class="text-xs font-semibold uppercase tracking-wide text-ink-muted">
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
        </p>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <button
            v-if="canResumeMemo"
            type="button"
            @click="resumeReport"
            :disabled="resuming || generating || dismissing"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 disabled:cursor-not-allowed focus-ring"
          >
            <Loader2 v-if="resuming" class="h-4 w-4 animate-spin" />
            <Sparkles v-else class="h-4 w-4" />
            <span>{{ resuming ? tr("research.resuming_memo") : tr("research.resume_memo") }}</span>
          </button>
          <button
            type="button"
            @click="dismissFailedReport"
            :disabled="resuming || generating || dismissing"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle text-ink-muted hover:bg-surface disabled:opacity-60 disabled:cursor-not-allowed focus-ring"
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
      v-if="canShowMemoStudio && activeTab === 'memo'"
      :company-id="companyId"
      @discuss="openMemoEditorDiscuss"
    />

    <section
      v-if="canShowMemoStudio && activeTab === 'memo'"
      class="mt-6 bg-surface border border-subtle rounded-card shadow-card p-6"
    >
      <details>
        <summary class="cursor-pointer text-sm font-semibold text-ink-primary focus-ring rounded">
          {{ tr("research.advanced_tools") }}
        </summary>
        <div class="mt-4">
          <MemoAnalysisDashboard
            :company-id="companyId"
            @generate-memo="generate"
          />
        </div>
      </details>
    </section>

    <section
      v-if="company && activeTab === 'memo'"
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

    <section
      v-if="company && activeTab === 'news'"
      class="bg-surface border border-subtle rounded-card shadow-card p-6"
    >
      <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="flex items-center gap-2">
            <div class="vogue-label">{{ tr("research.tab_news") }}</div>
            <span class="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent-soft px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent-ink">
              <span class="live-pulse h-1.5 w-1.5 rounded-full bg-accent"></span>
              {{ tr("research.news_live") }}
            </span>
          </div>
          <h2 class="mt-1 font-display text-xl font-bold text-ink-primary">
            {{ tr("research.news_feed_title") }}
          </h2>
          <p class="mt-1 text-sm text-ink-muted">
            {{ tr("research.news_feed_subtitle") }}
          </p>
        </div>
        <button
          type="button"
          class="pill-button border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          @click="$emit('open-copilot')"
        >
          {{ tr("research.news_submit_link") }}
        </button>
      </div>

      <form class="mb-4 flex flex-col gap-3" @submit.prevent="loadNewsFeed">
        <input
          v-model="newsSearch"
          type="search"
          :placeholder="tr('research.news_search_placeholder')"
          class="rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-sm text-ink-primary placeholder:text-ink-subtle focus-ring"
        />
        <div class="flex flex-wrap items-center gap-2" role="group" :aria-label="tr('research.news_filter_label')">
          <button
            v-for="filter in NEWS_FILTERS"
            :key="filter.value || 'all'"
            type="button"
            @click="selectNewsCategory(filter.value)"
            :class="[
              'rounded-full border px-3 py-1.5 text-xs font-semibold focus-ring',
              newsCategory === filter.value
                ? 'border-ink-primary bg-ink-primary text-white'
                : 'border-subtle bg-surface text-ink-secondary hover:bg-surface-muted',
            ]"
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
      <div v-else-if="companyNews.length === 0" class="rounded-row border border-subtle bg-surface-muted p-4 text-sm text-ink-muted">
        {{ newsFeed.empty_state || tr("research.news_empty") }}
      </div>
      <ul v-else class="space-y-3">
        <li
          v-for="item in companyNews"
          :key="item.id || item.headline || item.title"
          class="rounded-row border border-subtle bg-surface p-4"
        >
          <div class="flex items-start gap-3">
            <span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-accent"></span>
            <div class="min-w-0 flex-1">
              <div class="mono-data text-[11px] uppercase tracking-wide text-ink-muted">{{ newsMeta(item) }}</div>
              <div class="mt-1 text-sm font-semibold text-ink-primary">{{ item.title || item.headline }}</div>
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
              class="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted"
            >
              {{ tag }}
            </span>
          </div>
        </li>
      </ul>
    </section>

    <section
      v-if="company && activeTab === 'industry'"
      class="space-y-5"
    >
      <div class="rounded-card border border-subtle bg-surface p-6 shadow-card">
        <div class="vogue-label">{{ tr("research.tab_industry") }}</div>
        <h2 class="mt-1 font-display text-xl font-bold text-ink-primary">
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

      <div class="rounded-card border border-subtle bg-surface p-6 shadow-card">
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
                <span class="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide" :class="{
                  'bg-accent-soft text-accent-ink': opinion.stance === 'Bullish',
                  'bg-danger-soft text-danger-ink': opinion.stance === 'Cautious',
                  'bg-surface-muted text-ink-muted': opinion.stance !== 'Bullish' && opinion.stance !== 'Cautious',
                }">{{ opinion.stance || tr("research.industry_neutral") }}</span>
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
        <div class="rounded-card border border-subtle bg-surface p-6 shadow-card">
          <div class="vogue-label">{{ tr("research.industry_public_comps") }}</div>
          <div v-if="publicComps.length === 0" class="mt-3 text-sm text-ink-muted">
            {{ tr("research.industry_comps_empty") }}
          </div>
          <div v-else class="mt-4 space-y-3">
            <article
              v-for="comp in publicComps"
              :key="comp.id || comp.ticker"
              class="rounded-row border border-subtle bg-surface-muted p-4"
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

        <div class="rounded-card border border-subtle bg-surface p-6 shadow-card">
          <div class="vogue-label">{{ tr("research.industry_sector_signals") }}</div>
          <div v-if="sectorSignals.length === 0" class="mt-3 text-sm text-ink-muted">
            {{ tr("research.industry_signals_empty") }}
          </div>
          <div v-else class="mt-4 space-y-3">
            <article
              v-for="signal in sectorSignals"
              :key="signal.id || signal.signal"
              class="rounded-row border border-subtle bg-surface-muted p-4"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full bg-warning-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-warning-ink">
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
      :previewable-kinds="['pdf']"
      @close="closeMemoPreview"
    />
  </div>
</template>
