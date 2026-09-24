<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CirclePause,
  Download,
  FileText,
  FileWarning,
  Flag,
  Link2,
  Loader2,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import {
  activeJobs,
  refreshActiveJobs,
  subscribeActiveJobs,
  unsubscribeActiveJobs,
} from "../activeJobs.js";
import {
  cleanDisplayName,
  decisionWord,
  factCheckChip,
  hasPermission,
  isInternalSource,
  isMemoReport,
  memoJobChanges,
  memoJobSnapshot,
  qualityChip,
  reportCanOpen,
  reportHeadline,
  reportIsComplete,
  reportIsDocless,
  reportIsHidden,
  reportListStatus,
  reportState,
  reportTypeKey,
  reportTypeLabel,
  reviewChip,
  sourceLabel,
  spanLabel,
  toneClasses,
  useTwoStepArm,
  verdictChip,
  versionInfo,
} from "../reportStatus.js";
import AiMark from "../components/AiMark.vue";
import DocumentViewerWindow from "../components/DocumentViewerWindow.vue";
import Monogram from "../components/Monogram.vue";
import {
  copyText,
  loadReportPermissions,
  recordReportDownloaded,
  reportShareUrl,
  sessionPermissions,
} from "../components/reports/reportSession.js";
import { useLargeTitle, useMediaQuery } from "../chrome.js";

const t = useT();
const route = useRoute();
const router = useRouter();

// Two panes from `lg` up: the list beside the document, and the list can
// fold to a rail of logos (the Research Desk directory's move). Below `lg`
// the desk shows one pane at a time — the list, or the report its `?id`
// names, with a Back button — because a 320px list beside a phone-width
// viewer left the document a sliver.
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
// Dismissed failures and runs a newer run replaced stay out of the list
// unless asked for.
const showDismissed = ref(false);
const viewerFullscreen = ref(false);

// One pane at a time below `lg`: the viewer when the URL names a report.
const showList = computed(() => isSplitWidth.value || !route.query.id);
const showViewer = computed(() => isSplitWidth.value || Boolean(route.query.id));

const dateLocale = computed(() => (appLanguage.value === "zh" ? "zh-CN" : "en-US"));

function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(dateLocale.value, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function typeLabel(report) {
  return reportTypeLabel(report, t);
}

// ---- The reader's permissions -------------------------------------------------
// Export needs memo:export; the IC memo (internal) needs memo:edit to read.
// Unknown (not loaded yet) hides what they gate rather than offering a
// download the server will refuse.
const permissions = computed(() => sessionPermissions.value);
const canExport = computed(() => hasPermission(permissions.value, "memo:export"));
const canReadInternal = computed(() => hasPermission(permissions.value, "memo:edit"));

// A re-rendered document keeps its URL; its render stamp tells the viewer
// to fetch it again (the server ignores the extra parameter).
function withRenderStamp(url, report) {
  const stamp = String(report?.rendered_at || "").trim();
  if (!url || !stamp) return url;
  return `${url}${url.includes("?") ? "&" : "?"}r=${encodeURIComponent(stamp)}`;
}

function reportSources(report) {
  if (!report) return [];
  const order = { en: 0, zh: 1, internal: 2, internal_zh: 3 };
  const rawUrls = report.download_urls || {};
  const keys = Object.keys(rawUrls).filter((key) => !isInternalSource(key) || canReadInternal.value);
  const pdf = report.pdf_status || {};
  return keys
    .sort((a, b) => (order[a] ?? 9) - (order[b] ?? 9))
    .map((key) => {
      const internal = isInternalSource(key);
      const lang = String(key).toLowerCase();
      return {
        key: String(key).toUpperCase(),
        // The internal document is the IC decision memo: it reads as that,
        // not as a language code.
        label: sourceLabel(key, keys, t),
        hint: internal ? t("reports.source_ic_memo_hint") : "",
        url: withRenderStamp(rawUrls[key], report),
        kind: "docx",
        // The PDF, only once it is ready: never wait on one to read.
        pdfUrl:
          !internal && (lang === "en" || lang === "zh") && pdf[lang] === "ready"
            ? withRenderStamp(api.reportPdfUrl(report.id, lang), report)
            : "",
      };
    });
}

function formatReportCompanyName(r) {
  if (!r) return "";
  const name = cleanDisplayName(r.company_name);
  if (name && name !== "x") return name;
  if (r.company_id && r.company_id !== "x") {
    return r.company_id;
  }
  return t("research.report_type.investment_report");
}

// ---- What each row says ------------------------------------------------------------

function rowVerdict(r) {
  return verdictChip(r, t, appLanguage.value);
}

function rowHeadline(r) {
  return reportHeadline(r, appLanguage.value);
}

function rowReview(r) {
  return reviewChip(r, t, appLanguage.value);
}

function rowFact(r) {
  return factCheckChip(r, t);
}

function rowVersion(r) {
  return versionInfo(r);
}

function changedFromLabel(r) {
  const from = versionInfo(r).changedFrom;
  return from ? decisionWord(from, r, t) : "";
}

function openFlags(r) {
  return Number(r?.open_flags) || 0;
}

function hasIcMemo(r) {
  return Object.keys(r?.download_urls || {}).some((key) => isInternalSource(key));
}

// Whether the row's line of chips (review, gates, flags, versions) has any.
function rowHasChips(r) {
  return Boolean(
    rowReview(r) ||
      reportState(r) === "warnings" ||
      hasIcMemo(r) ||
      r?.structure_version === "v2" ||
      qualityChip(r, t) ||
      openFlags(r) ||
      rowFact(r) ||
      changedFromLabel(r) ||
      r?.dismissed_at ||
      r?.superseded_by,
  );
}

// The row's explicit downloads: purpose=export, logged and gated.
function rowDownloads(r) {
  if (!canExport.value || !isMemoReport(r)) return [];
  const urls = r?.download_urls || {};
  return ["en", "zh"]
    .filter((lang) => urls[lang])
    .map((lang) => ({
      lang,
      label: lang.toUpperCase(),
      title: lang === "en" ? t("research.download_en") : t("research.download_zh"),
      href: api.reportExportUrl(r.id, lang),
    }));
}

function onRowDownload(r, lang) {
  recordReportDownloaded(r.id, lang, "reports_list:docx");
}

// The workspace's own record for a report's company, if it has one. Most
// reports belong to companies that were never added here; their desk link
// would open some other company, so they get plain text instead.
function workspaceCompanyFor(r) {
  const cid = String(r?.company_id || "");
  if (!cid) return null;
  const list = workspaceCompanies.value || [];
  return (
    list.find((c) => c.id === cid) ||
    list.find((c) => c.ticker && String(c.ticker).toLowerCase() === cid.toLowerCase()) ||
    null
  );
}

function reportCompany(r) {
  if (!r) return {};
  const cid = r.company_id || "";
  const match = workspaceCompanyFor(r);
  return {
    ...(match || {}),
    id: r.company_id,
    name: formatReportCompanyName(r),
    ticker: r.ticker || match?.ticker || (cid && cid.length <= 5 && !cid.includes("-") ? cid.toUpperCase() : null),
    logo_url: r.logo_url || match?.logo_url,
    logo_domain: r.logo_domain || match?.logo_domain,
    website: r.website || match?.website,
    // The identity the report took of its company at creation; the logo
    // resolver prefers it (companyLogo.js), so a later rename or a
    // lookalike never changes the logo on an old memo.
    company_identity:
      r.company_identity && typeof r.company_identity === "object" ? r.company_identity : match?.company_identity,
  };
}

async function loadReports({ quiet = false } = {}) {
  if (!quiet) loading.value = true;
  if (!quiet) error.value = null;
  try {
    const list = await api.listReports();
    reports.value = Array.isArray(list) ? list : [];
    error.value = null;
    // A link to a cleared or replaced report still opens it.
    const deepId = String(route.query.id || "");
    const deep = deepId ? reports.value.find((r) => r.id === deepId) : null;
    if (deep && reportIsHidden(deep)) showDismissed.value = true;
    // Nothing chosen: open the newest report that has something to read.
    if (!selectedReportId.value && reports.value.length > 0) {
      const visible = reports.value.filter((r) => !reportIsHidden(r));
      const firstReady = visible.find((r) => reportIsComplete(r) && reportCanOpen(r));
      selectedReportId.value = (firstReady || visible[0] || reports.value[0]).id;
    }
  } catch (e) {
    if (!quiet) error.value = e?.message || t("reports.load_failed");
  } finally {
    loading.value = false;
  }
}

function reportMatchesFilters(r) {
  const q = searchQuery.value.trim().toLowerCase();
  const company = selectedCompany.value;
  const status = selectedStatus.value;
  const kind = selectedKind.value;
  if (company !== "all" && r.company_id !== company) return false;
  if (status !== "all" && reportListStatus(r) !== status) return false;
  if (kind !== "all" && reportTypeKey(r) !== kind) return false;
  if (q) {
    // The call and its headline too, in both languages: "pass" finds the
    // memos that pass.
    const headline = r.reader?.headline || {};
    const haystack = [
      r.company_name,
      formatReportCompanyName(r),
      r.company_id,
      r.report_type,
      r.kind,
      typeLabel(r),
      r.decision || r.reader?.decision,
      rowVerdict(r)?.label,
      headline.en,
      headline.zh,
    ].map((value) => String(value || "").toLowerCase());
    if (!haystack.some((value) => value.includes(q))) return false;
  }
  return true;
}

const visibleReports = computed(() =>
  showDismissed.value ? reports.value : reports.value.filter((r) => !reportIsHidden(r)),
);

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

// Report types present, labelled from report_type (an Auto run keeps its
// own name after it resolves to the late-stage kind).
const kindOptions = computed(() => {
  const map = new Map();
  for (const r of reports.value) {
    const key = reportTypeKey(r);
    if (key && !map.has(key)) map.set(key, typeLabel(r));
  }
  return Array.from(map.entries()).map(([id, label]) => ({ id, label }));
});

const matchingReports = computed(() => reports.value.filter(reportMatchesFilters));

// Filtered reports
const filteredReports = computed(() =>
  showDismissed.value
    ? matchingReports.value
    : matchingReports.value.filter((r) => !reportIsHidden(r)),
);

const hiddenCount = computed(
  () => matchingReports.value.filter((r) => reportIsHidden(r)).length,
);

// ---- Versions: older memos fold under their latest (R24) -------------------
// The server marks, per company and kind, which finished memo is the latest
// and what each one's latest is. An older version folds under its latest
// when that row is on the list; otherwise (filtered out) it stands alone.
const expandedGroups = ref(new Set());

const listRows = computed(() => {
  const shown = new Set(filteredReports.value.map((r) => r.id));
  const older = new Map();
  const top = [];
  for (const r of filteredReports.value) {
    const v = versionInfo(r);
    if (v.grouped && !v.isLatest && v.latestId && v.latestId !== r.id && shown.has(v.latestId)) {
      if (!older.has(v.latestId)) older.set(v.latestId, []);
      older.get(v.latestId).push(r);
    } else {
      top.push(r);
    }
  }
  return top.map((r) => ({ report: r, older: older.get(r.id) || [] }));
});

// The rows as drawn: each latest memo, and under it its older versions
// while its group is open. The collapsed rail shows the same reports.
const flatRows = computed(() => {
  const out = [];
  for (const row of listRows.value) {
    out.push({ report: row.report, older: row.older.length, nested: false });
    if (row.older.length && expandedGroups.value.has(row.report.id)) {
      for (const report of row.older) out.push({ report, older: 0, nested: true });
    }
  }
  return out;
});

const railReports = computed(() => flatRows.value.map((row) => row.report));

function toggleGroup(id) {
  const next = new Set(expandedGroups.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expandedGroups.value = next;
}

function earlierLabel(count) {
  return count === 1
    ? t("reports.version.earlier_one")
    : t("reports.version.earlier_many", { count });
}

// ---- A row's overflow menu: Open Studio, Copy link -------------------------------
const rowMenuId = ref("");
const rowMenuUp = ref(false);
const rowLinkCopied = ref("");
const rowLinkFallback = ref("");
let rowLinkTimer = null;

function toggleRowMenu(r, event) {
  if (rowMenuId.value === r.id) {
    rowMenuId.value = "";
    return;
  }
  rowLinkFallback.value = "";
  rowLinkCopied.value = "";
  // Near the bottom of the list the menu opens upward rather than under
  // the list's edge.
  const button = event?.currentTarget;
  const list = button?.closest?.("[data-testid='reports-list-rows']");
  if (button?.getBoundingClientRect && list?.getBoundingClientRect) {
    rowMenuUp.value = list.getBoundingClientRect().bottom - button.getBoundingClientRect().bottom < 150;
  } else {
    rowMenuUp.value = false;
  }
  rowMenuId.value = r.id;
}

async function copyRowLink(r) {
  const url = reportShareUrl(r.id, appLanguage.value === "zh" ? "zh" : "en");
  const ok = await copyText(url);
  clearTimeout(rowLinkTimer);
  if (ok) {
    rowLinkFallback.value = "";
    rowLinkCopied.value = r.id;
    rowLinkTimer = setTimeout(() => {
      rowLinkCopied.value = "";
      rowMenuId.value = "";
    }, 1200);
  } else {
    rowLinkFallback.value = url;
  }
}

function onListPointerDown(event) {
  if (!rowMenuId.value) return;
  const inside = event.target?.closest?.("[data-row-menu]");
  if (!inside) rowMenuId.value = "";
}

// Currently selected report object
const activeReport = computed(() => {
  return reports.value.find((r) => r.id === selectedReportId.value) || null;
});

// Sources for active report
const activeSources = computed(() => {
  return reportSources(activeReport.value);
});

const activeCompany = computed(() => workspaceCompanyFor(activeReport.value));

// The version before the open memo, for "Changes since <its date>".
const activePreviousVersion = computed(() => {
  const id = activeReport.value?.previous_version_id;
  return id ? reports.value.find((r) => r.id === id) || null : null;
});

// An older version opened by a link or the rail shows under its latest.
watch(
  [selectedReportId, listRows],
  ([id, rows]) => {
    if (!id) return;
    const holder = rows.find((row) => row.older.some((r) => r.id === id));
    if (holder && !expandedGroups.value.has(holder.report.id)) {
      expandedGroups.value = new Set([...expandedGroups.value, holder.report.id]);
    }
  },
  { immediate: true },
);

// Where the reader came from, for the viewer's report_opened event.
const openSource = ref(route.query.id ? "deep_link" : "reports_default");

const activeTitle = computed(() =>
  activeReport.value
    ? `${formatReportCompanyName(activeReport.value)} — ${typeLabel(activeReport.value)}`
    : "",
);

// Summary counters
const stats = computed(() => {
  let complete = 0;
  let running = 0;
  let attention = 0;
  let failed = 0;
  for (const r of visibleReports.value) {
    const s = reportListStatus(r);
    if (s === "complete") complete++;
    else if (s === "running") running++;
    else if (s === "needs_attention") attention++;
    else if (s === "failed") failed++;
  }
  return {
    total: visibleReports.value.length,
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

// ---- The selected report's detail (working papers, live-log URLs) --------
// Fetched once per version of a memo record, never for the whole list: the
// detail scans the run folder.
const detailCache = new Map();
const activeDetail = ref(null);

watch(
  () => {
    const r = activeReport.value;
    return r && isMemoReport(r) ? `${r.id}|${r.status}|${r.updated_at || ""}` : "";
  },
  async (key) => {
    const report = activeReport.value;
    if (!key || !report) {
      activeDetail.value = null;
      return;
    }
    if (detailCache.has(key)) {
      activeDetail.value = detailCache.get(key);
      return;
    }
    if (activeDetail.value?.id !== report.id) activeDetail.value = null;
    try {
      const detail = await api.getReport(report.id);
      detailCache.set(key, detail);
      if (activeReport.value?.id === report.id) activeDetail.value = detail;
    } catch {
      // No papers or log link then; the document itself still opens.
    }
  },
  { immediate: true },
);

// ---- Selection and the URL -----------------------------------------------

let pushedFromList = false;

function selectReport(report) {
  const changed = report.id !== selectedReportId.value;
  if (changed) openSource.value = "reports_list";
  rowMenuId.value = "";
  selectedReportId.value = report.id;
  const query = { ...route.query, id: report.id };
  if (changed) {
    delete query.section;
    delete query.paper;
  }
  // On a phone the list and the report are two screens, so Back returns.
  if (!isSplitWidth.value) {
    pushedFromList = true;
    router.push({ query });
  } else {
    router.replace({ query });
  }
}

function backToList() {
  if (pushedFromList) {
    pushedFromList = false;
    router.back();
    return;
  }
  const query = { ...route.query };
  delete query.id;
  delete query.section;
  delete query.paper;
  router.replace({ query });
}

function replaceQuery(patch) {
  const query = { ...route.query };
  for (const [key, value] of Object.entries(patch)) {
    if (value) query[key] = value;
    else delete query[key];
  }
  const same =
    Object.keys(query).length === Object.keys(route.query).length &&
    Object.entries(query).every(([key, value]) => route.query[key] === value);
  if (!same) router.replace({ query });
}

// The document opens in the language the app speaks unless the URL names
// one; picking a language writes it back (replace, so no history entries).
const initialLanguageKey = computed(() =>
  String(route.query.lang || (appLanguage.value === "zh" ? "ZH" : "EN")),
);

function onChangeSource(source) {
  if (!source?.userInitiated || !source.key) return;
  replaceQuery({ lang: String(source.key).toLowerCase() });
}

function onChangeSection(key) {
  replaceQuery({ section: key });
}

function onSelectPaper(filename) {
  replaceQuery({ paper: filename || "" });
}

function toggleFullscreen() {
  viewerFullscreen.value = !viewerFullscreen.value;
}

function onKeydown(event) {
  if (rowMenuId.value && event.key === "Escape") {
    rowMenuId.value = "";
    return;
  }
  if (!viewerFullscreen.value) return;
  const key = String(event.key || "").toLowerCase();
  // Escape leaves full screen; ⌘N leaves it too, so the Generate dialog the
  // app opens is not hidden under the document.
  if (key === "escape" || ((event.metaKey || event.ctrlKey) && key === "n")) {
    viewerFullscreen.value = false;
  }
}

watch(
  () => route.query.id,
  (newId) => {
    if (newId && newId !== selectedReportId.value) {
      selectedReportId.value = String(newId);
      const deep = reports.value.find((r) => r.id === newId);
      if (deep && reportIsHidden(deep)) showDismissed.value = true;
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

// ---- Live refresh ------------------------------------------------------------
// The jobs rail already polls /api/jobs/active; the list rides on that one
// poll. When a memo run finishes, fails, turns ready or starts somewhere
// else, the list reloads quietly, so a finished run stops reading Running.
let jobSnapshot = memoJobSnapshot(activeJobs.value);

watch(activeJobs, (jobs) => {
  const next = memoJobSnapshot(jobs);
  const { finished, ready, started } = memoJobChanges(jobSnapshot, next);
  jobSnapshot = next;
  const known = new Set(reports.value.map((r) => r.id));
  if (finished.length || ready.length || started.some((id) => !known.has(id))) {
    loadReports({ quiet: true });
  }
});

function onReportChanged() {
  loadReports({ quiet: true });
}

// A run paused after its English memo continues from its row: the resume
// endpoint (the viewer's Resume makes the same call) writes the Chinese,
// the artifacts and the IC memo. Two clicks, as every paid action here.
const continueArm = useTwoStepArm();
const continuingId = ref("");
const continueErrorId = ref("");

async function continuePaused(r) {
  const id = r?.id;
  if (!id || continuingId.value) return;
  if (!continueArm.trigger(id)) return;
  continuingId.value = id;
  continueErrorId.value = "";
  try {
    await api.resumeReport(id);
    await refreshActiveJobs();
    await loadReports({ quiet: true });
  } catch {
    continueErrorId.value = id;
  } finally {
    continuingId.value = "";
  }
}

function continueLabel(r) {
  if (continuingId.value === r.id) return t("research.resuming_memo");
  if (continueArm.armed.value === r.id) return t("reports.status_card.continue_confirm");
  return t("reports.status_card.continue_chinese");
}

onMounted(() => {
  subscribeActiveJobs();
  window.addEventListener("keydown", onKeydown);
  document.addEventListener("pointerdown", onListPointerDown);
  loadReportPermissions();
  loadReports();
});

onBeforeUnmount(() => {
  unsubscribeActiveJobs();
  window.removeEventListener("keydown", onKeydown);
  document.removeEventListener("pointerdown", onListPointerDown);
  clearTimeout(rowLinkTimer);
});
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
        v-if="showList"
        class="desk-card flex shrink-0 flex-col overflow-hidden"
        :class="listCollapsed ? 'w-[44px]' : isSplitWidth ? 'w-80 lg:w-[22rem]' : 'w-full'"
        data-testid="reports-list"
      >
        <!-- Collapsed: a rail of the reports' company logos, the way the
             sidebar collapses to its own. The open report's logo sits lifted;
             each opens its report; the button at the top brings the list back. -->
        <div v-if="listCollapsed" class="flex h-full w-full flex-col items-center gap-1 py-2">
          <button
            type="button"
            class="icon-btn !h-7 !w-7 shrink-0"
            :aria-label="t('reports.expand_list')"
            :title="t('reports.expand_list')"
            :aria-expanded="false"
            data-testid="reports-list-expand"
            @click="toggleList"
          >
            <PanelLeftOpen class="h-4 w-4 shrink-0" />
            <span class="sr-only">
              {{ t("reports.total_count", { count: filteredReports.length }) }}
            </span>
          </button>
          <div class="reports-rail" data-testid="reports-rail">
            <button
              v-for="r in railReports"
              :key="r.id"
              type="button"
              class="reports-rail-mark focus-ring"
              :data-selected="r.id === selectedReportId ? 'true' : 'false'"
              :title="`${formatReportCompanyName(r)} — ${typeLabel(r)}`"
              :aria-label="`${formatReportCompanyName(r)} — ${typeLabel(r)}`"
              :aria-current="r.id === selectedReportId ? 'true' : undefined"
              @click="selectReport(r)"
            >
              <Monogram :company="reportCompany(r)" :size="26" tinted aria-hidden="true" />
            </button>
          </div>
        </div>

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
              data-testid="reports-kind-filter"
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
          <button
            v-if="hiddenCount > 0"
            type="button"
            class="mt-2 text-caption1 font-medium text-accent-ink hover:underline focus-ring"
            data-testid="reports-show-dismissed"
            @click="showDismissed = true"
          >
            {{ t("reports.show_dismissed", { count: hiddenCount }) }}
          </button>
        </div>

        <div v-else class="flex-1 space-y-0.5 overflow-y-auto px-1.5 pb-1.5" data-testid="reports-list-rows">
          <article
            v-for="{ report: r, older, nested } in flatRows"
            :key="r.id"
            class="doc-row relative"
            :class="nested ? 'reports-row-nested' : ''"
            :data-selected="r.id === selectedReportId ? 'true' : 'false'"
            :data-report-id="r.id"
            :data-nested="nested ? 'true' : null"
            @click="selectReport(r)"
          >
            <Monogram
              :company="reportCompany(r)"
              :size="nested ? 26 : 34"
              tinted
              class="mt-0.5"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-baseline justify-between gap-2">
                <div class="flex min-w-0 items-baseline gap-1.5">
                  <span class="truncate text-callout font-semibold text-ink-primary">
                    {{ formatReportCompanyName(r) }}
                  </span>
                  <span
                    v-if="rowVersion(r).isLatest && rowVersion(r).count > 1"
                    class="shrink-0 rounded-[5px] bg-accent-soft px-1.5 py-px text-caption2 font-semibold text-accent-ink"
                    :title="t('reports.version.latest_hint')"
                    data-testid="report-latest"
                  >
                    {{ t("reports.version.latest") }}
                  </span>
                  <span
                    v-else-if="nested && rowVersion(r).count > 1"
                    class="shrink-0 text-caption2 text-ink-muted tabular"
                    data-testid="report-version"
                  >
                    {{ t("reports.version.of", { index: rowVersion(r).index, count: rowVersion(r).count }) }}
                  </span>
                </div>
                <span class="shrink-0 text-caption1 text-ink-muted tabular">
                  {{ fmtDate(r.created_at) }}
                </span>
              </div>

              <div class="mt-0.5 flex items-center justify-between gap-2">
                <div class="flex min-w-0 items-center gap-1.5">
                  <h3 class="truncate text-footnote text-ink-secondary" :title="typeLabel(r)">
                    {{ typeLabel(r) }}
                  </h3>
                </div>
                <!-- A finished memo's state is its review chip below; the
                     line keeps its downloads. Other rows say where they are. -->
                <div class="flex shrink-0 items-center gap-1 text-caption1">
                  <span
                    v-if="reportIsDocless(r)"
                    class="chip shrink-0 bg-ink-primary/[0.06] text-ink-secondary"
                    data-testid="report-status-docless"
                  >
                    <FileWarning class="h-3 w-3" />
                    {{ t("reports.status_no_document") }}
                  </span>
                  <span
                    v-else-if="reportListStatus(r) === 'complete' && !isMemoReport(r)"
                    class="chip shrink-0 bg-success-soft text-success-ink"
                  >
                    <CheckCircle2 class="h-3 w-3" />
                    {{ t("reports.status_complete") }}
                  </span>
                  <span
                    v-else-if="reportListStatus(r) === 'running'"
                    class="chip shrink-0 bg-info-soft text-info-ink"
                  >
                    <Loader2 class="h-3 w-3 animate-spin" />
                    {{ t("reports.status_running") }}
                  </span>
                  <span
                    v-else-if="reportState(r) === 'cards_ready'"
                    class="chip shrink-0 bg-warning-soft text-warning-ink"
                  >
                    <AlertCircle class="h-3 w-3" />
                    {{ t("reports.status_cards_ready") }}
                  </span>
                  <template v-else-if="reportState(r) === 'paused'">
                    <span
                      class="chip shrink-0 bg-notice-soft text-notice-ink"
                      :title="r.stage || null"
                      data-testid="report-status-paused"
                    >
                      <CirclePause class="h-3 w-3" />
                      {{ t("reports.status_paused") }}
                    </span>
                    <button
                      type="button"
                      class="btn-filled btn-sm focus-ring shrink-0 !px-2 !py-0.5 !text-caption1"
                      :disabled="continuingId === r.id"
                      :title="continueErrorId === r.id ? t('reports.status_card.action_failed') : null"
                      data-testid="report-continue"
                      @click.stop="continuePaused(r)"
                    >
                      {{ continueLabel(r) }}
                    </button>
                  </template>
                  <span
                    v-else-if="reportListStatus(r) === 'failed'"
                    class="chip shrink-0 bg-danger-soft text-danger-ink"
                  >
                    {{ t("reports.status_failed") }}
                  </span>

                  <a
                    v-for="download in rowDownloads(r)"
                    :key="download.lang"
                    :href="download.href"
                    download
                    class="inline-flex items-center gap-0.5 rounded-[5px] px-1 text-ink-muted hover:bg-ink-primary/[0.06] hover:text-ink-primary"
                    :title="download.title"
                    :data-testid="`report-download-${download.lang}`"
                    @click.stop="onRowDownload(r, download.lang)"
                  >
                    <Download class="h-3 w-3" />
                    <span>{{ download.label }}</span>
                  </a>

                  <!-- Open Studio and Copy link, out of the row's way. -->
                  <div class="relative" data-row-menu>
                    <button
                      type="button"
                      class="grid h-5 w-5 place-items-center rounded-[5px] text-ink-muted hover:bg-ink-primary/[0.06] hover:text-ink-primary focus-ring"
                      :title="t('reports.row_more')"
                      :aria-label="t('reports.row_more')"
                      aria-haspopup="menu"
                      :aria-expanded="rowMenuId === r.id"
                      data-testid="report-row-more"
                      @click.stop="toggleRowMenu(r, $event)"
                    >
                      <MoreHorizontal class="h-3.5 w-3.5" />
                    </button>
                    <div
                      v-if="rowMenuId === r.id"
                      class="toolbar-menu !min-w-[12.5rem]"
                      :data-up="rowMenuUp ? 'true' : null"
                      role="menu"
                      data-testid="report-row-menu"
                      @click.stop
                    >
                      <RouterLink
                        v-if="workspaceCompanyFor(r)"
                        :to="{ name: 'research', params: { companyId: workspaceCompanyFor(r).id }, query: { section: 'memos', report: r.id } }"
                        class="toolbar-menu-item"
                        role="menuitem"
                        data-testid="report-open-studio"
                        @click="rowMenuId = ''"
                      >
                        <Sparkles class="h-3.5 w-3.5 text-ink-muted" />
                        {{ t("reports.open_report") }}
                      </RouterLink>
                      <button
                        type="button"
                        class="toolbar-menu-item"
                        role="menuitem"
                        data-testid="report-copy-link"
                        @click="copyRowLink(r)"
                      >
                        <CheckCircle2 v-if="rowLinkCopied === r.id" class="h-3.5 w-3.5 text-success" />
                        <Link2 v-else class="h-3.5 w-3.5 text-ink-muted" />
                        {{ rowLinkCopied === r.id ? t("viewer.link_copied") : t("viewer.copy_link") }}
                      </button>
                      <div v-if="rowLinkFallback" class="px-2.5 pb-1.5 pt-0.5">
                        <div class="text-caption1 text-ink-muted">{{ t("viewer.copy_failed") }}</div>
                        <input
                          class="field field-sm mt-1 w-full"
                          readonly
                          :value="rowLinkFallback"
                          :aria-label="t('viewer.copy_link')"
                          @focus="$event.target.select()"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- What it concludes: the call and its opening sentence. -->
              <div v-if="rowVerdict(r) || rowHeadline(r)" class="mt-1 flex min-w-0 items-center gap-1.5">
                <span
                  v-if="rowVerdict(r)"
                  class="inline-flex shrink-0 items-center rounded-[5px] px-1.5 py-px text-caption2 font-semibold"
                  :class="toneClasses(rowVerdict(r).tone)"
                  :title="rowVerdict(r).title"
                  data-testid="report-verdict"
                >
                  {{ rowVerdict(r).label }}
                </span>
                <p
                  v-if="rowHeadline(r)"
                  class="min-w-0 truncate text-caption1 text-ink-muted"
                  :title="rowHeadline(r)"
                  data-testid="report-headline"
                >
                  {{ rowHeadline(r) }}
                </p>
              </div>

              <div
                v-if="rowHasChips(r)"
                class="mt-1.5 flex items-center justify-between gap-2 text-caption1"
              >
                <div class="flex min-w-0 flex-wrap items-center gap-1">
                  <span
                    v-if="rowReview(r)"
                    class="inline-flex items-center rounded-[5px] px-1.5 py-px text-caption2 font-semibold"
                    :class="toneClasses(rowReview(r).tone)"
                    :title="rowReview(r).title"
                    data-testid="report-review"
                  >
                    {{ rowReview(r).label }}
                  </span>
                  <span
                    v-if="reportState(r) === 'warnings'"
                    class="inline-flex items-center gap-0.5 rounded-[5px] bg-warning-soft px-1.5 py-px text-caption2 font-semibold text-warning-ink"
                    data-testid="report-attention"
                  >
                    <AlertCircle class="h-2.5 w-2.5" />
                    {{ t("reports.status_needs_attention") }}
                  </span>
                  <span
                    v-if="hasIcMemo(r)"
                    class="rounded-[5px] bg-ink-primary/[0.06] px-1.5 py-px text-caption2 font-semibold text-ink-secondary"
                    :title="t('reports.source_ic_memo_hint')"
                    data-testid="report-ic-memo"
                  >
                    {{ t("reports.source_ic_memo") }}
                  </span>
                  <span
                    v-if="r.structure_version === 'v2'"
                    class="rounded-[5px] bg-accent-soft px-1.5 py-px text-caption2 font-semibold text-accent-ink"
                    :title="t('reports.ic_template_tag_hint')"
                    data-testid="report-ic-template"
                  >
                    {{ t("reports.ic_template_tag") }}
                  </span>
                  <span
                    v-if="qualityChip(r, t)"
                    class="inline-flex items-center gap-0.5 rounded-[5px] px-1.5 py-px text-caption2 font-semibold tabular"
                    :class="qualityChip(r, t).flagged ? 'bg-warning-soft text-warning-ink' : 'bg-success-soft text-success-ink'"
                    :title="qualityChip(r, t).title"
                    data-testid="quality-chip"
                  >
                    <Sparkles class="h-2.5 w-2.5" />
                    {{ qualityChip(r, t).label }}
                  </span>
                  <span
                    v-if="openFlags(r)"
                    class="inline-flex items-center gap-0.5 rounded-[5px] bg-warning-soft px-1.5 py-px text-caption2 font-semibold text-warning-ink tabular"
                    :title="openFlags(r) === 1 ? t('comments.flag_count_one') : t('comments.flag_count', { count: openFlags(r) })"
                    data-testid="report-open-flags"
                  >
                    <Flag class="h-2.5 w-2.5" />
                    {{ openFlags(r) }}
                  </span>
                  <span
                    v-if="rowFact(r)"
                    class="inline-flex items-center gap-0.5 rounded-[5px] px-1.5 py-px text-caption2 font-semibold tabular"
                    :class="toneClasses(rowFact(r).tone)"
                    :title="rowFact(r).title"
                    :data-state="rowFact(r).state"
                    data-testid="fact-check-chip"
                  >
                    <ShieldCheck class="h-2.5 w-2.5" />
                    {{ rowFact(r).label }}
                  </span>
                  <span
                    v-if="changedFromLabel(r)"
                    class="inline-flex items-center gap-0.5 rounded-[5px] bg-warning-soft px-1.5 py-px text-caption2 font-semibold text-warning-ink"
                    :title="
                      rowVersion(r).unstable
                        ? t('reports.version.unstable_hint', { span: spanLabel(rowVersion(r).flipDays, t) })
                        : t('reports.version.changed_from_hint', { verdict: changedFromLabel(r) })
                    "
                    :data-unstable="rowVersion(r).unstable ? 'true' : null"
                    data-testid="report-changed-from"
                  >
                    <TriangleAlert v-if="rowVersion(r).unstable" class="h-2.5 w-2.5" />
                    {{
                      rowVersion(r).unstable
                        ? t("reports.version.unstable_was", { verdict: changedFromLabel(r) })
                        : t("reports.version.changed_from", { verdict: changedFromLabel(r) })
                    }}
                  </span>
                  <span
                    v-if="r.dismissed_at || r.superseded_by"
                    class="rounded-[5px] bg-ink-primary/[0.06] px-1.5 py-px text-caption2 font-medium text-ink-muted"
                  >
                    {{ r.superseded_by ? t("reports.superseded_tag") : t("reports.dismissed_tag") }}
                  </span>
                </div>
              </div>

              <!-- Older memos of the same company and kind fold under the latest. -->
              <button
                v-if="older"
                type="button"
                class="mt-1 inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-caption1 font-medium text-accent-ink transition-colors hover:bg-accent/[0.08] focus-ring"
                :aria-expanded="expandedGroups.has(r.id)"
                data-testid="report-earlier-toggle"
                @click.stop="toggleGroup(r.id)"
              >
                <ChevronDown v-if="expandedGroups.has(r.id)" class="h-3 w-3" />
                <ChevronRight v-else class="h-3 w-3" />
                {{ expandedGroups.has(r.id) ? t("reports.version.hide_earlier") : earlierLabel(older) }}
              </button>
            </div>
          </article>
          <div v-if="hiddenCount > 0" class="flex justify-center py-2">
            <button
              type="button"
              class="rounded-full px-2.5 py-1 text-caption1 font-medium text-accent-ink transition-colors hover:bg-accent/[0.08] focus-ring"
              data-testid="reports-show-dismissed"
              @click="showDismissed = !showDismissed"
            >
              {{ showDismissed ? t("reports.hide_dismissed") : t("reports.show_dismissed", { count: hiddenCount }) }}
            </button>
          </div>
        </div>
        </template>
      </aside>

      <!-- Full screen moves this same viewer to the top of the page, so the
           zoom, the language and the reading position come along. -->
      <Teleport to="body" :disabled="!viewerFullscreen">
        <section
          v-if="showViewer"
          class="desk-card flex h-full min-w-0 flex-1 flex-col overflow-hidden"
          :class="viewerFullscreen ? 'reports-viewer-fullscreen' : ''"
          data-testid="reports-viewer"
        >
          <DocumentViewerWindow
            :title="activeTitle"
            :company-name="formatReportCompanyName(activeReport)"
            :company-id="activeCompany?.id || activeReport?.company_id || ''"
            :company-linkable="Boolean(activeCompany)"
            :report-id="activeReport?.id || ''"
            :date="fmtDate(activeReport?.created_at)"
            :sources="activeSources"
            :initial-key="initialLanguageKey"
            :report="activeReport"
            :detail="activeDetail"
            :active-paper="String(route.query.paper || '')"
            :initial-section="String(route.query.section || '')"
            :fullscreen="viewerFullscreen"
            :show-back="!isSplitWidth && !viewerFullscreen"
            :permissions="permissions"
            :previous-version="activePreviousVersion"
            :event-source="openSource"
            :company="activeReport ? reportCompany(activeReport) : null"
            @open-fullscreen="toggleFullscreen"
            @change-source="onChangeSource"
            @change-section="onChangeSection"
            @select-paper="onSelectPaper"
            @back="backToList"
            @report-changed="onReportChanged"
          />
        </section>
      </Teleport>
    </div>
  </div>
</template>
