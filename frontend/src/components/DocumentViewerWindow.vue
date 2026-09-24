<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  ArrowLeft,
  CircleAlert,
  CirclePause,
  Download,
  ExternalLink,
  FileText,
  FileWarning,
  Flag,
  History,
  Loader2,
  Maximize2,
  MessageSquare,
  Minimize2,
  MoveHorizontal,
  NotebookText,
  RefreshCw,
  Sparkles,
  TableOfContents,
  TriangleAlert,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-vue-next";
import MarkdownIt from "markdown-it";
import { renderAsync } from "docx-preview";
import { RouterLink } from "vue-router";
import { useT } from "../i18n.js";
import { api, withApiToken } from "../api.js";
import { appLanguage } from "../state.js";
import { useMediaQuery } from "../chrome.js";
import { activeJobs, refreshActiveJobs } from "../activeJobs.js";
import {
  ZOOM_MAX,
  ZOOM_MIN,
  clampZoom,
  docxPageWidth,
  fitZoom,
  nextZoomStep,
} from "../docxFit.js";
import {
  decisionWord,
  hasPermission,
  isFailedPaperText,
  isInternalSource,
  isMemoReport,
  isPlaceholderType,
  memoJobFor,
  qualityMetricsLine,
  reportFailureDetail,
  reportFailureSummary,
  reportFailureTitle,
  reportFreshness,
  reportIsComplete,
  reportState,
  reportWarnings,
  requestJobLog,
  reviewActions,
  reviewChip,
  reviewRenderNote,
  sourceLanguage,
  spanLabel,
  toneClasses,
  useTwoStepArm,
  verdictChip,
  versionInfo,
  warningLanguages,
} from "../reportStatus.js";
import Monogram from "./Monogram.vue";
import ReportChangesPanel from "./reports/ReportChangesPanel.vue";
import ReportCommentsPanel from "./reports/ReportCommentsPanel.vue";
import ReportExportMenu from "./reports/ReportExportMenu.vue";
import ReportMoreMenu from "./reports/ReportMoreMenu.vue";
import {
  copyText,
  recordReportDownloaded,
  recordReportOpened,
  reportShareUrl,
  sessionPermissions,
} from "./reports/reportSession.js";

const props = defineProps({
  title: { type: String, default: "" },
  companyName: { type: String, default: "" },
  companyId: { type: String, default: "" },
  // False when the company is not in this workspace: its desk would open on
  // some other company, so the name is plain text rather than a link.
  companyLinkable: { type: Boolean, default: true },
  reportId: { type: String, default: "" },
  date: { type: String, default: "" },
  // [{ key, url, kind, label? }] — kind: "docx" | "md" | "text".
  sources: { type: Array, default: () => [] },
  initialKey: { type: String, default: "" },
  allowClose: { type: Boolean, default: false },
  // Optional: the report's ReportSummary. With no document on file the
  // viewer shows the run's status instead of an empty page, and a memo that
  // finished with warnings gets a banner naming what was flagged.
  report: { type: Object, default: null },
  // Optional: its ReportDetail (GET /api/reports/{id}), for the working
  // papers and the run's live-log URLs.
  detail: { type: Object, default: null },
  // The working paper on screen (its filename), or "" for the memo.
  activePaper: { type: String, default: "" },
  // A section to open at (`?section=`): a bookmark id or an outline ordinal.
  initialSection: { type: String, default: "" },
  fullscreen: { type: Boolean, default: false },
  showBack: { type: Boolean, default: false },
  // The reader's permissions (GET /api/auth/me → permissions). A memo's
  // Export needs memo:export, comments and flags memo:edit, review moves
  // memo:edit / memo:approve. null while unknown: those controls wait.
  permissions: { type: Array, default: null },
  // The previous finished memo of the same company and kind, if the list
  // has it: "Changes since <its date>".
  previousVersion: { type: Object, default: null },
  // Where the reader came from, sent with report_opened.
  eventSource: { type: String, default: "reports_viewer" },
  // The company as the list draws it (logo_url / logo_domain / ticker /
  // company_identity), so the header shows the same logo as the row.
  company: { type: Object, default: null },
});

const emit = defineEmits([
  "close",
  "open-fullscreen",
  "change-source",
  "change-section",
  "select-paper",
  "back",
  "report-changed",
]);
const t = useT();
const openReportCustomizer = inject("openReportCustomizer", null);

// html: false keeps raw HTML in markdown inert
const markdown = new MarkdownIt({ html: false, linkify: true });

const activeIndex = ref(0);
const loading = ref(false);
const loadError = ref(false);
const renderedKind = ref("");
const markdownHtml = ref("");
const textContent = ref("");
const docxContainer = ref(null);
const scrollArea = ref(null);

function nextFrame() {
  return new Promise((resolve) => {
    if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(() => resolve());
    } else {
      setTimeout(resolve, 0);
    }
  });
}

// A Word page is laid out at its own width (Letter is 816px) and scaled.
// Fit to width is the default: the page widens with the window and keeps its
// layout. − and +, a trackpad pinch, or the percentage (actual size) set a
// zoom by hand instead; the choice is this browser's, kept between reports.
const ZOOM_KEY = "bsh.docViewerZoom";

function readZoomChoice() {
  try {
    const raw = window.localStorage.getItem(ZOOM_KEY);
    if (!raw || raw === "fit") return "fit";
    const value = Number(raw);
    return Number.isFinite(value) ? clampZoom(value) : "fit";
  } catch {
    return "fit";
  }
}

const zoomChoice = ref(readZoomChoice()); // "fit" or a zoom picked by hand
const fitValue = ref(1);
const isFit = computed(() => zoomChoice.value === "fit");
const docxZoom = computed(() => (isFit.value ? fitValue.value : zoomChoice.value));
const zoomPercent = computed(() => `${Math.round(docxZoom.value * 100)}%`);
let docxPage = 0;
let resizeObserver = null;

watch(zoomChoice, (choice) => {
  try {
    window.localStorage.setItem(ZOOM_KEY, String(choice));
  } catch {
    // localStorage unavailable: the zoom lasts for this visit only
  }
});

function fitDocx() {
  const area = scrollArea.value;
  if (!area || !docxPage || typeof getComputedStyle !== "function") return;
  const style = getComputedStyle(area);
  const available =
    area.clientWidth - parseFloat(style.paddingLeft || 0) - parseFloat(style.paddingRight || 0);
  // Fit means the whole page width shows, down to a phone's width: below
  // the zoom buttons' 50% floor rather than a page cut off at the right.
  if (available > 0) fitValue.value = fitZoom(available, docxPage, { min: 0.3 });
}

/**
 * Change the zoom and keep the point under `anchor` (the pointer for a pinch,
 * else the middle of the view) where it was, the way Preview zooms.
 */
function setZoom(choice, anchor) {
  const area = scrollArea.value;
  const before = docxZoom.value;
  zoomChoice.value = choice === "fit" ? "fit" : clampZoom(choice);
  const after = docxZoom.value;
  if (!area || !before || after === before) return;
  const ratio = after / before;
  const x = anchor?.x ?? area.clientWidth / 2;
  const y = anchor?.y ?? area.clientHeight / 2;
  const left = area.scrollLeft;
  const top = area.scrollTop;
  nextTick(() => {
    area.scrollLeft = (left + x) * ratio - x;
    area.scrollTop = (top + y) * ratio - y;
  });
}

const zoomIn = () => setZoom(nextZoomStep(docxZoom.value, 1));
const zoomOut = () => setZoom(nextZoomStep(docxZoom.value, -1));

// A trackpad pinch arrives as a wheel event with ctrlKey set.
function onWheel(event) {
  if (!event.ctrlKey || renderedKind.value !== "docx" || !scrollArea.value) return;
  event.preventDefault();
  const box = scrollArea.value.getBoundingClientRect();
  setZoom(docxZoom.value * Math.exp(-event.deltaY * 0.01), {
    x: event.clientX - box.left,
    y: event.clientY - box.top,
  });
}

// The title usually names the company already; then its link is just the
// arrow beside the title rather than the name a second time.
const titleNamesCompany = computed(() => {
  const name = String(props.companyName || "").trim().toLowerCase();
  return Boolean(name) && String(props.title || "").toLowerCase().includes(name);
});

// The header's logo reads the same identity as the list row: the company the
// page hands over, else the report's own logo fields and its identity
// snapshot (companyLogo.js prefers company_identity).
const headerCompany = computed(() => {
  if (props.company && typeof props.company === "object") {
    return { ...props.company, id: props.company.id || props.companyId, name: props.company.name || props.companyName };
  }
  const report = props.report || {};
  return {
    id: props.companyId,
    name: props.companyName,
    logo_url: report.logo_url || undefined,
    logo_domain: report.logo_domain || undefined,
    company_identity:
      report.company_identity && typeof report.company_identity === "object" ? report.company_identity : undefined,
  };
});

const companyLinkTitle = computed(() =>
  props.companyName
    ? `${t("reports.open_company")}: ${props.companyName}`
    : t("reports.open_company"),
);

// ---- Working papers ----------------------------------------------------------
// The run's analysis passes (countercase, pressure tests, claim register…),
// read through the same markdown path as any other source. One menu, not a
// pill per paper: a run can carry fifteen of them.

const papers = computed(() => {
  const list = props.detail?.analysis_artifacts;
  return Array.isArray(list) ? list.filter((p) => p?.filename && p?.download_url) : [];
});
const activePaperObj = computed(() =>
  props.activePaper ? papers.value.find((p) => p.filename === props.activePaper) || null : null,
);
const papersOpen = ref(false);
const papersMenu = ref(null);
// Papers found to be a failed pass's placeholder once loaded, by URL (the
// same filename belongs to every run).
const failedPapers = ref(new Set());
const paperIsPlaceholder = ref(false);

function paperDidNotRun(paper) {
  return paper?.failed === true || failedPapers.value.has(paper?.download_url);
}

function choosePaper(paper) {
  papersOpen.value = false;
  emit("select-paper", paper?.filename || "");
}

function onDocPointerDown(event) {
  if (papersOpen.value && papersMenu.value && !papersMenu.value.contains(event.target)) {
    papersOpen.value = false;
  }
}

// ---- Sources ---------------------------------------------------------------

function activeSource() {
  return props.sources[activeIndex.value] || null;
}

const activeSourceObj = computed(() => props.sources[activeIndex.value] || null);
// The language of the document on screen (en | zh); the IC memo is English
// unless its key says otherwise.
const activeLanguage = computed(() => sourceLanguage(activeSourceObj.value?.key) || "");

function resolveInitialIndex() {
  if (props.initialKey && props.sources.length) {
    const idx = props.sources.findIndex(
      (s) => s.key.toLowerCase() === props.initialKey.toLowerCase(),
    );
    if (idx >= 0) return idx;
  }
  return 0;
}

// ---- Permissions ---------------------------------------------------------------

const permissionList = computed(() => props.permissions ?? sessionPermissions.value);
const isMemo = computed(() => Boolean(props.report) && isMemoReport(props.report));
const finishedMemo = computed(() => isMemo.value && reportIsComplete(props.report));
// A memo's export is gated (memo:export, G8); a plain document is not.
const canExport = computed(() => !isMemo.value || hasPermission(permissionList.value, "memo:export"));
const canComment = computed(() => finishedMemo.value && hasPermission(permissionList.value, "memo:edit"));

// ---- PDF or web view (R25) ---------------------------------------------------------
// A memo whose PDF is ready opens as the PDF — paginated, page-numbered, as
// it prints and forwards. The docx render stays one click away for the
// outline, zoom and flagging, and is what shows while a PDF is not ready:
// reading never waits on a PDF.

const VIEW_MODE_KEY = "bsh.docViewerMode";

function readViewMode() {
  try {
    return window.localStorage.getItem(VIEW_MODE_KEY) === "web" ? "web" : "pdf";
  } catch {
    return "pdf";
  }
}

const viewMode = ref(readViewMode());
const pdfSrc = ref("");
const pdfFrame = ref(null);

function sourceUsesPdf(source) {
  if (!source) return false;
  if (source.kind === "pdf") return Boolean(source.url);
  return Boolean(source.pdfUrl) && viewMode.value === "pdf";
}

const offersPdf = computed(
  () => !activePaperObj.value && Boolean(activeSourceObj.value?.pdfUrl) && activeSourceObj.value?.kind !== "pdf",
);

function setViewMode(mode) {
  if (mode === viewMode.value) return;
  viewMode.value = mode;
  try {
    window.localStorage.setItem(VIEW_MODE_KEY, mode);
  } catch {
    // the choice lasts for this visit only
  }
  loadSource();
}

// A working paper downloads as itself; purpose=export marks it an explicit
// export, which the server logs (and gates on memo:export).
function exportUrl(url) {
  if (!url) return "";
  if (!isMemo.value || /[?&]purpose=/.test(url)) return withApiToken(url);
  return withApiToken(`${url}${url.includes("?") ? "&" : "?"}purpose=export`);
}

const exportHref = computed(() => {
  if (!canExport.value) return "";
  if (activePaperObj.value) return exportUrl(activePaperObj.value.download_url);
  const url = activeSource()?.url;
  return url ? withApiToken(url) : "";
});

// The Export menu for a memo: PDF for sharing (when ready), Word, both
// languages as a .zip — explicit exports (purpose=export).
const exportOptions = computed(() => {
  const report = props.report;
  const source = activeSourceObj.value;
  if (!report?.id || !source || !isMemo.value || !canExport.value) return [];
  const key = String(source.key || "").toLowerCase();
  if (isInternalSource(key)) {
    const language = sourceLanguage(key) || "en";
    return [
      {
        id: "docx",
        label: t("viewer.export_docx"),
        hint: t("viewer.export_docx_hint"),
        href: api.reportExportUrl(report.id, language, "internal"),
        language: "",
        format: "ic_docx",
      },
    ];
  }
  const language = sourceLanguage(key);
  if (!language) return [];
  const options = [];
  const pdf = report.pdf_status || {};
  if (pdf[language] === "ready") {
    const url = api.reportPdfUrl(report.id, language);
    options.push({
      id: "pdf",
      label: t("viewer.export_pdf"),
      hint: t("viewer.export_pdf_hint"),
      href: `${url}${url.includes("?") ? "&" : "?"}purpose=export`,
      language,
      format: "pdf",
    });
  }
  options.push({
    id: "docx",
    label: t("viewer.export_docx"),
    hint: t("viewer.export_docx_hint"),
    href: api.reportExportUrl(report.id, language),
    language,
    format: "docx",
  });
  const urls = report.download_urls || {};
  if (urls.en && urls.zh) {
    const withPdf = pdf.en === "ready" && pdf.zh === "ready";
    options.push({
      id: "zip",
      label: t("viewer.export_zip"),
      hint: withPdf ? t("viewer.export_zip_hint_all") : t("viewer.export_zip_hint_docx"),
      href: api.reportBundleUrl(report.id, withPdf ? "all" : "docx"),
      language: "",
      format: "zip",
    });
  }
  return options;
});

function onExportSelect(option) {
  recordReportDownloaded(props.report?.id, option?.language, `${props.eventSource}:${option?.format || "file"}`);
}

function onPaperExport() {
  if (props.report?.id && activePaperObj.value) {
    recordReportDownloaded(props.report.id, "", `${props.eventSource}:paper`);
  }
}

// ---- Reading telemetry ---------------------------------------------------------

function noteOpened(source) {
  const id = props.report?.id;
  if (!id || !source || !isMemo.value) return;
  const key = String(source.key || "");
  const internal = isInternalSource(key);
  recordReportOpened(
    id,
    internal ? "" : sourceLanguage(key),
    internal ? `${props.eventSource}:ic_memo` : props.eventSource,
  );
}

function onPdfLoad() {
  if (renderedKind.value === "pdf") noteOpened(activeSourceObj.value);
}

let loadToken = 0;
// The docx rendered into the container, kept while a working paper is read
// so "Back to memo" returns to the same place without a reload.
let docxUrl = "";
let memoScroll = null;
// Where to put the reader after the next docx render: the same place in the
// other language, or a `?section=` deep link.
let pendingPosition = null;
let pendingSection = "";
// A language pill pressed while a working paper is open: the memo load that
// follows is the reader's choice, so it may update the page's ?lang.
let nextLoadUserInitiated = false;

function clearDocx() {
  docxUrl = "";
  docxPage = 0;
  outline.value = [];
  outlineEls = [];
  activeSection.value = "";
  if (docxContainer.value) docxContainer.value.innerHTML = "";
}

async function loadPaper(paper, token) {
  loadError.value = false;
  markdownHtml.value = "";
  textContent.value = "";
  if (paper.failed === true) {
    // The server already knows this pass did not run: nothing to fetch.
    paperIsPlaceholder.value = true;
    loading.value = false;
    renderedKind.value = "md";
    return;
  }
  loading.value = true;
  paperIsPlaceholder.value = false;
  renderedKind.value = "";
  try {
    const response = await fetch(withApiToken(paper.download_url));
    if (token !== loadToken) return;
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const text = await response.text();
    if (token !== loadToken) return;
    if (isFailedPaperText(text)) {
      // A pass that failed leaves a stub holding a raw CLI error: say it
      // did not run instead of printing the error.
      paperIsPlaceholder.value = true;
      failedPapers.value = new Set([...failedPapers.value, paper.download_url]);
    } else {
      markdownHtml.value = markdown.render(text);
    }
    renderedKind.value = "md";
    await nextTick();
    if (scrollArea.value) scrollArea.value.scrollTop = 0;
  } catch {
    if (token !== loadToken) return;
    loadError.value = true;
    renderedKind.value = "";
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

async function loadSource(options = {}) {
  const userInitiated = Boolean(options.userInitiated || nextLoadUserInitiated);
  nextLoadUserInitiated = false;
  const token = ++loadToken;
  const area = scrollArea.value;
  const paper = activePaperObj.value;
  if (paper) {
    if (renderedKind.value === "docx" && area) {
      memoScroll = { top: area.scrollTop, left: area.scrollLeft };
    }
    await loadPaper(paper, token);
    return;
  }
  paperIsPlaceholder.value = false;
  markdownHtml.value = "";
  textContent.value = "";
  const source = activeSource();
  if (!source?.url) {
    renderedKind.value = "";
    clearDocx();
    loading.value = false;
    loadError.value = Boolean(props.sources.length);
    return;
  }
  if (sourceUsesPdf(source)) {
    // The PDF is the browser's to render: an <iframe>, no fetch here. The
    // docx render (if any) stays underneath for "Web".
    if (renderedKind.value === "docx" && area) {
      memoScroll = { top: area.scrollTop, left: area.scrollLeft };
    }
    pdfSrc.value = source.kind === "pdf" ? source.url : source.pdfUrl;
    renderedKind.value = "pdf";
    loadError.value = false;
    loading.value = false;
    emit("change-source", { ...source, userInitiated });
    return;
  }
  if (source.kind === "docx" && docxUrl === source.url && docxContainer.value?.childElementCount) {
    // Back from a working paper: the memo is still rendered underneath.
    loadError.value = false;
    loading.value = false;
    renderedKind.value = "docx";
    await nextTick();
    if (memoScroll && scrollArea.value) {
      scrollArea.value.scrollTop = memoScroll.top;
      scrollArea.value.scrollLeft = memoScroll.left;
    }
    memoScroll = null;
    return;
  }
  memoScroll = null;
  clearDocx();
  renderedKind.value = "";
  loading.value = true;
  loadError.value = false;
  try {
    const response = await fetch(withApiToken(source.url));
    if (token !== loadToken) return;
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (source.kind === "docx") {
      const buffer = await response.arrayBuffer();
      if (token !== loadToken) return;
      renderedKind.value = "docx";
      await nextTick();
      if (docxContainer.value) {
        await renderAsync(buffer, docxContainer.value, undefined, {
          inWrapper: true,
          ignoreLastRenderedPageBreak: true,
        });
        if (token !== loadToken) return;
        docxUrl = source.url;
        docxPage = docxPageWidth(docxContainer.value.querySelector("section.docx"));
        prepareLinks(docxContainer.value);
        fitDocx();
        buildOutline();
        noteOpened(source);
      }
    } else if (source.kind === "md") {
      const text = await response.text();
      if (token !== loadToken) return;
      markdownHtml.value = markdown.render(text);
      renderedKind.value = "md";
    } else {
      const text = await response.text();
      if (token !== loadToken) return;
      textContent.value = text;
      renderedKind.value = "text";
    }
    emit("change-source", { ...source, userInitiated });
  } catch {
    if (token !== loadToken) return;
    loadError.value = true;
    renderedKind.value = "";
  } finally {
    if (token === loadToken) loading.value = false;
  }
  if (token === loadToken && renderedKind.value === "docx") await placeReader(token);
}

function selectSource(index) {
  if (activePaperObj.value) {
    // A language pill while a paper is open goes back to the memo in it.
    activeIndex.value = index;
    nextLoadUserInitiated = true;
    choosePaper(null);
    return;
  }
  if (index === activeIndex.value) return;
  // Keep the reader at the same section in the other language.
  pendingPosition = capturePosition();
  activeIndex.value = index;
  loadSource({ userInitiated: true });
}

function onFullscreen() {
  emit("open-fullscreen", {
    title: props.title || t("documents.viewer_title"),
    sources: props.sources,
    activeIndex: activeIndex.value,
  });
}

// ---- Links inside the document --------------------------------------------

// External links open in a new tab; in-document anchors (the TOC, [S#]/[C#]
// citations) scroll this viewer instead of touching the app's URL.
function prepareLinks(root) {
  for (const link of root.querySelectorAll("a[href]")) {
    if (/^https?:\/\//i.test(link.getAttribute("href") || "")) {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    }
  }
}

function decodeAnchor(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function onContentClick(event) {
  const link = event.target?.closest?.("a[href]");
  if (!link || !scrollArea.value?.contains(link)) return;
  const href = link.getAttribute("href") || "";
  if (href.startsWith("#")) {
    event.preventDefault();
    const id = decodeAnchor(href.slice(1));
    const target = id ? document.getElementById(id) : null;
    if (target && docxContainer.value?.contains(target)) {
      scrollToElement(target.closest("p") || target);
    }
    return;
  }
  if (/^https?:\/\//i.test(href)) {
    event.preventDefault();
    window.open(href, "_blank", "noopener,noreferrer");
  }
}

// ---- Outline -----------------------------------------------------------------
// Built from the renderer's section bookmarks (bsh_sec_*, the same ids in EN
// and ZH), else Word heading styles (Buffett memos), else — older late-stage
// memos with neither — the large bold section titles.

const outline = ref([]); // [{ key, label, level }]
let outlineEls = []; // the elements, kept out of reactive state
const activeSection = ref("");
const OUTLINE_KEY = "bsh.docViewerOutline";
const mediumUp = useMediaQuery("(min-width: 768px)", true);
// Until someone chooses, the outline opens only where the page keeps a
// readable width beside it: the viewer's own width, not the window's.
const bodyEl = ref(null);
const bodyWidth = ref(0);
const OUTLINE_ROOM = 1100;
// A narrow viewer drops the date and the papers button's label from the
// header, so the title keeps room to be read.
const compactHeader = computed(
  () => props.sources.length > 0 && bodyWidth.value > 0 && bodyWidth.value < 900,
);

function readOutlinePref() {
  try {
    const raw = window.localStorage.getItem(OUTLINE_KEY);
    if (raw === "1") return true;
    if (raw === "0") return false;
  } catch {
    // no stored choice
  }
  return null;
}

const outlinePref = ref(readOutlinePref());
const outlineOpen = computed(() =>
  outlinePref.value == null ? bodyWidth.value >= OUTLINE_ROOM : outlinePref.value,
);
const outlineAvailable = computed(
  () =>
    renderedKind.value === "docx" &&
    !loading.value &&
    !loadError.value &&
    outline.value.length > 0,
);
const outlineVisible = computed(() => outlineOpen.value && outlineAvailable.value);

async function keepPlaceThrough(change) {
  const position = capturePosition();
  change();
  if (!position) return;
  await nextTick();
  await nextFrame();
  await nextFrame();
  restorePosition(position);
}

function toggleOutline() {
  keepPlaceThrough(() => {
    outlinePref.value = !outlineOpen.value;
    try {
      window.localStorage.setItem(OUTLINE_KEY, outlinePref.value ? "1" : "0");
    } catch {
      // the choice lasts for this visit only
    }
  });
}

function entryLabel(el) {
  const text = (node) => String(node?.textContent || "").replace(/\s+/g, " ").trim();
  let label = text(el);
  if (!label) label = text(el.nextElementSibling);
  return label.length > 90 ? `${label.slice(0, 88)}…` : label;
}

function runSizePt(span) {
  const size = String(span.style?.fontSize || "");
  const pt = size.match(/^([\d.]+)pt$/);
  if (pt) return Number(pt[1]);
  const px = size.match(/^([\d.]+)px$/);
  return px ? Number(px[1]) * 0.75 : 0;
}

function isBoldRun(span) {
  const weight = String(span.style?.fontWeight || "");
  return weight === "bold" || Number(weight) >= 600;
}

function boldTitleEntries(root) {
  const candidates = [];
  for (const p of root.querySelectorAll("p")) {
    if (p.closest("table")) continue;
    const text = String(p.textContent || "").replace(/\s+/g, " ").trim();
    if (text.length < 2 || text.length > 90) continue;
    const runs = [...p.querySelectorAll("span")].filter(
      (span) => span.children.length === 0 && String(span.textContent || "").trim(),
    );
    if (!runs.length || !runs.every(isBoldRun)) continue;
    const size = Math.max(...runs.map(runSizePt));
    if (size < 12) continue;
    candidates.push({ el: p, size });
  }
  // The section titles share one size; the cover's larger lines do not.
  const counts = new Map();
  for (const c of candidates) counts.set(c.size, (counts.get(c.size) || 0) + 1);
  let best = 0;
  let bestCount = 0;
  for (const [size, count] of counts) {
    if (count > bestCount) {
      best = size;
      bestCount = count;
    }
  }
  if (bestCount < 3) return [];
  return candidates
    .filter((c) => c.size === best)
    .map((c, index) => ({ key: String(index + 1), el: c.el, level: 1 }));
}

function buildOutline() {
  const root = docxContainer.value;
  let entries = [];
  if (root) {
    const marks = [...root.querySelectorAll('[id^="bsh_sec_"]')];
    if (marks.length) {
      entries = marks.map((mark) => ({ key: mark.id, el: mark.closest("p") || mark, level: 1 }));
    }
    if (!entries.length) {
      entries = [...root.querySelectorAll(".docx_heading1, .docx_heading2")].map((el, index) => ({
        key: String(index + 1),
        el,
        level: el.classList.contains("docx_heading2") ? 2 : 1,
      }));
    }
    if (!entries.length) entries = boldTitleEntries(root);
  }
  const items = [];
  const els = [];
  for (const entry of entries) {
    const label = entryLabel(entry.el);
    if (!label) continue;
    items.push({ key: entry.key, label, level: entry.level });
    els.push(entry.el);
  }
  outlineEls = els;
  outline.value = items;
  activeSection.value = "";
}

function sectionOffsets() {
  const area = scrollArea.value;
  if (!area) return [];
  const top = area.getBoundingClientRect().top;
  return outlineEls.map((el) => area.scrollTop + el.getBoundingClientRect().top - top);
}

function currentSectionIndex() {
  const area = scrollArea.value;
  if (!area || !outlineEls.length) return -1;
  const areaTop = area.getBoundingClientRect().top;
  let index = -1;
  for (let i = 0; i < outlineEls.length; i += 1) {
    if (outlineEls[i].getBoundingClientRect().top - areaTop <= 32) index = i;
    else break;
  }
  return index;
}

function updateActiveSection() {
  const index = currentSectionIndex();
  activeSection.value = index >= 0 ? outline.value[index]?.key || "" : "";
}

let spyScheduled = false;
function onScroll() {
  // The Flag button sits over the selection it was made for.
  if (flagButton.value) flagButton.value = null;
  if (spyScheduled || !outlineEls.length) return;
  spyScheduled = true;
  nextFrame().then(() => {
    spyScheduled = false;
    updateActiveSection();
  });
}

function prefersReducedMotion() {
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

// getBoundingClientRect reads the page as drawn, so the CSS zoom on the
// Word page is already in the numbers.
function scrollToElement(el, smooth = true) {
  const area = scrollArea.value;
  if (!area || !el) return;
  const top = Math.max(0, area.scrollTop + el.getBoundingClientRect().top - area.getBoundingClientRect().top - 8);
  if (smooth && typeof area.scrollTo === "function" && !prefersReducedMotion()) {
    area.scrollTo({ top, behavior: "smooth" });
  } else {
    area.scrollTop = top;
  }
}

function findEntry(key) {
  const wanted = String(key || "");
  if (!wanted) return -1;
  const exact = outline.value.findIndex((entry) => entry.key === wanted);
  if (exact >= 0) return exact;
  // A bookmark id on a document without bookmarks, or an ordinal on one
  // with them: fall back to the position.
  const ordinal = wanted.match(/^(?:bsh_sec_)?(\d+)$/);
  if (ordinal) {
    const index = Number(ordinal[1]) - 1;
    if (index >= 0 && index < outline.value.length) return index;
  }
  return -1;
}

function goToSection(entry) {
  const index = outline.value.findIndex((e) => e.key === entry.key);
  if (index < 0) return;
  scrollToElement(outlineEls[index]);
  activeSection.value = entry.key;
  emit("change-section", entry.key);
  if (!mediumUp.value) outlinePref.value = false;
}

function capturePosition() {
  const area = scrollArea.value;
  if (!area || renderedKind.value !== "docx") return null;
  const index = currentSectionIndex();
  if (index < 0) {
    return { ratio: area.scrollHeight > 0 ? area.scrollTop / area.scrollHeight : 0 };
  }
  const offsets = sectionOffsets();
  const start = offsets[index];
  const end = index + 1 < offsets.length ? offsets[index + 1] : area.scrollHeight;
  const fraction = (area.scrollTop - start) / Math.max(1, end - start);
  return {
    key: outline.value[index]?.key,
    index,
    fraction: Math.min(1, Math.max(0, fraction)),
  };
}

function restorePosition(position) {
  const area = scrollArea.value;
  if (!area || !position) return;
  if (position.key != null && outlineEls.length) {
    let index = outline.value.findIndex((entry) => entry.key === position.key);
    if (index < 0 && position.index < outlineEls.length) index = position.index;
    if (index >= 0) {
      const offsets = sectionOffsets();
      const start = offsets[index];
      const end = index + 1 < offsets.length ? offsets[index + 1] : area.scrollHeight;
      area.scrollTop = start + position.fraction * (end - start);
      updateActiveSection();
      return;
    }
  }
  if (position.ratio != null) area.scrollTop = position.ratio * area.scrollHeight;
}

async function placeReader(token) {
  await nextTick();
  await nextFrame();
  if (token !== loadToken) return;
  if (pendingPosition) {
    const position = pendingPosition;
    pendingPosition = null;
    restorePosition(position);
    return;
  }
  if (pendingSection) {
    const index = findEntry(pendingSection);
    pendingSection = "";
    if (index >= 0) {
      scrollToElement(outlineEls[index], false);
      activeSection.value = outline.value[index].key;
    }
  }
}

// ---- Status (no document yet, or none at all) -----------------------------

const reportStateValue = computed(() => (props.report ? reportState(props.report) : ""));
const liveJob = computed(() => memoJobFor(activeJobs.value, props.report?.id));

const statusKind = computed(() => {
  if (!props.report || props.sources.length) return "";
  const state = reportStateValue.value;
  if (state === "running") return "running";
  if (state === "failed") return "failed";
  if (state === "cards_ready") return "cards_ready";
  if (state === "paused") return "paused";
  return "docless";
});

// A run paused after its English memo, with that memo open: the strip
// under the header carries the Continue action instead of the card.
const pausedStrip = computed(
  () => Boolean(props.report) && props.sources.length > 0 && reportStateValue.value === "paused",
);

// memo_quality_metrics, when the run recorded them: traced %, sections over
// cap, conflicting figures, repetition — each with a one-line tooltip.
const qualityMetrics = computed(() => (props.report ? qualityMetricsLine(props.report, t) : null));

const statusTitle = computed(() => {
  const report = props.report;
  switch (statusKind.value) {
    case "running":
      return t("reports.status_card.running_title");
    case "failed":
      return reportFailureTitle(report, t);
    case "cards_ready":
      return t("research.status_cards_ready");
    case "paused":
      return t("reports.status_card.paused_title");
    case "docless":
      return t("reports.status_card.docless_title");
    default:
      return "";
  }
});

const runningStage = computed(() => {
  const stage = liveJob.value?.latest_stage || props.report?.stage || "";
  return String(stage).trim();
});

const runningProgress = computed(() => {
  const job = liveJob.value;
  if (job?.thread_count) {
    const settled = (job.thread_done_count || 0) + (job.thread_failed_count || 0);
    return Math.round((settled / job.thread_count) * 100);
  }
  const progress = Number(props.report?.progress);
  return Number.isFinite(progress) && progress > 0 ? Math.min(100, Math.round(progress)) : null;
});

function fmtDuration(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value) || value <= 0) return "";
  const totalS = Math.floor(value / 1000);
  if (totalS < 60) return `${totalS}s`;
  const m = Math.floor(totalS / 60);
  if (m < 60) return `${m}m ${totalS % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

const runningElapsed = computed(() => {
  const duration = fmtDuration(liveJob.value?.elapsed_ms);
  return duration ? t("jobs.modal.elapsed_duration", { duration }) : "";
});

// The rail's transcript modal for this run: the live job if the poll has
// it, else the run's own log and stream URLs from its detail record.
const logJob = computed(() => {
  if (liveJob.value) return liveJob.value;
  const detail = props.detail;
  if (!detail?.log_url && !detail?.stream_url) return null;
  return {
    kind: "memo",
    title: props.title,
    report_id: props.report?.id,
    company_id: props.report?.company_id,
    log_url: detail.log_url,
    stream_url: detail.stream_url,
  };
});

const failureSummary = computed(() => reportFailureSummary(props.report, appLanguage.value));

const failureDetail = computed(() => {
  const detail = reportFailureDetail(props.report);
  return detail && detail !== statusTitle.value && detail !== failureSummary.value ? detail : "";
});

const failureStage = computed(() => {
  const stage = String(props.report?.stage || "").trim();
  return stage && stage !== statusTitle.value && stage !== failureDetail.value ? stage : "";
});

// What the run spent before it stopped (API-equivalent), when recorded.
const failureSpend = computed(() => {
  const value = Number(props.report?.failure_spend_usd);
  return Number.isFinite(value) && value > 0 ? value.toFixed(2) : "";
});

const failedAtLabel = computed(() => {
  const raw = props.report?.updated_at || props.report?.created_at;
  const parsed = Date.parse(raw || "");
  if (Number.isNaN(parsed)) return "";
  return new Date(parsed).toLocaleString(appLanguage.value === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
});

const doclessBody = computed(() =>
  isPlaceholderType(props.report)
    ? t("reports.status_card.placeholder_body")
    : t("reports.status_card.docless_body"),
);

// Cancel, Resume and Clear each ask twice: the first click arms the button
// for four seconds, the second acts (the jobs rail's Cancel does the same).
const arm = useTwoStepArm();
const actionBusy = ref("");
const actionError = ref("");

watch(
  () => props.report?.id,
  () => {
    arm.reset();
    actionBusy.value = "";
    actionError.value = "";
  },
);

const ACTIONS = {
  cancel: (id) => api.cancelReportRun(id),
  resume: (id) => api.resumeReport(id),
  dismiss: (id) => api.dismissReport(id),
};

async function runAction(action) {
  const id = props.report?.id;
  if (!id || actionBusy.value) return;
  if (!arm.trigger(action)) return;
  actionBusy.value = action;
  actionError.value = "";
  try {
    await ACTIONS[action](id);
    await refreshActiveJobs();
    emit("report-changed", { action, id });
  } catch {
    actionError.value = t("reports.status_card.action_failed");
  } finally {
    actionBusy.value = "";
  }
}

function actionLabel(action) {
  // On a paused run, Resume is "Continue": the Chinese, artifacts and IC memo.
  const paused = reportStateValue.value === "paused";
  if (actionBusy.value === action) {
    if (action === "cancel") return t("jobs.cancelling");
    if (action === "resume") return t("research.resuming_memo");
    return t("research.dismissing");
  }
  if (arm.armed.value === action) {
    if (action === "cancel") return t("jobs.cancel_confirm");
    if (action === "resume") {
      return paused ? t("reports.status_card.continue_confirm") : t("reports.status_card.resume_confirm");
    }
    return t("reports.status_card.dismiss_confirm");
  }
  if (action === "cancel") return t("jobs.cancel");
  if (action === "resume") {
    return paused ? t("reports.status_card.continue_chinese") : t("research.resume_memo");
  }
  return t("research.dismiss_failed");
}

function openLog() {
  if (logJob.value) requestJobLog(logJob.value);
}

function newReport() {
  if (props.fullscreen) onFullscreen();
  openReportCustomizer?.(props.companyLinkable && props.companyId ? props.companyId : null);
}

// ---- Warnings (complete_with_warnings) ------------------------------------
// A slim banner naming the gate, the language and the section, and a dot on
// the flagged language's pill. It never switches language by itself: the
// Chinese team reads ZH, and a checker's false positive must not move them.

const hiddenWarnings = ref(new Set());
const warningItems = computed(() =>
  props.report ? reportWarnings(props.report, t, appLanguage.value) : [],
);
const warningKeys = computed(() => warningLanguages(warningItems.value));
const showWarnings = computed(
  () =>
    warningItems.value.length > 0 &&
    !activePaperObj.value &&
    !hiddenWarnings.value.has(props.report?.id),
);
const visibleWarnings = computed(() => warningItems.value.slice(0, 3));

function hideWarnings() {
  hiddenWarnings.value = new Set([...hiddenWarnings.value, props.report?.id]);
}

function languageName(code) {
  if (code === "ZH") return t("research.preview_zh");
  if (code === "EN") return t("research.preview_en");
  return "";
}

const icTemplate = computed(() => props.report?.structure_version === "v2");

// ---- What the memo concludes, its review and its freshness (R20, R24, G2) ---------
// A slim line under the header for a finished memo: the call, the review
// state, when it was written (amber once it is over a month old), and
// whether the call changed from the previous memo — plus the two panels.

const verdict = computed(() => (props.report ? verdictChip(props.report, t, appLanguage.value) : null));
const review = computed(() => (props.report ? reviewChip(props.report, t, appLanguage.value) : null));
const freshness = computed(() =>
  props.report ? reportFreshness(props.report, t, appLanguage.value, Date.now()) : null,
);
const version = computed(() => versionInfo(props.report || {}));
const changedFrom = computed(() =>
  version.value.changedFrom ? decisionWord(version.value.changedFrom, props.report, t) : "",
);
const flipSpan = computed(() => spanLabel(version.value.flipDays, t));
const renderNote = computed(() => (props.report ? reviewRenderNote(props.report, t) : ""));
const showMeta = computed(() => finishedMemo.value && props.sources.length > 0);
const openItems = computed(
  () => (Number(props.report?.open_comments) || 0) + (Number(props.report?.open_flags) || 0),
);
const canCompare = computed(() => finishedMemo.value && Boolean(version.value.previousId));
const changesLabel = computed(() =>
  previousDate.value ? t("viewer.changes_since", { date: previousDate.value }) : t("viewer.changes"),
);
const previousDate = computed(() => {
  const raw = props.previousVersion?.created_at;
  const parsed = Date.parse(raw || "");
  if (Number.isNaN(parsed)) return "";
  return new Date(parsed).toLocaleDateString(appLanguage.value === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
  });
});

// ---- Side panels: comments and flags, or the changes since the last memo -------

const sidePanel = ref(""); // "" | "comments" | "changes"
const flagDraft = ref(null); // { quote, label, language }
const flagButton = ref(null); // { x, y, quote, label, language }
const flagSent = ref(false);
let flagSentTimer = null;

const currentSection = computed(() => {
  const key = activeSection.value;
  if (!key) return null;
  const entry = outline.value.find((item) => item.key === key);
  return entry ? { key: entry.key, label: entry.label } : null;
});

// Beside the page when the viewer is wide, over it otherwise.
const panelOverlay = computed(() => bodyWidth.value > 0 && bodyWidth.value < 1000);

function togglePanel(name) {
  sidePanel.value = sidePanel.value === name ? "" : name;
  if (sidePanel.value !== "comments") flagDraft.value = null;
}

function closePanel() {
  sidePanel.value = "";
  flagDraft.value = null;
}

function onCommentsChanged() {
  emit("report-changed", { action: "comments", id: props.report?.id });
}

function onFlagDone({ sent } = {}) {
  flagDraft.value = null;
  if (sent) {
    flagSent.value = true;
    clearTimeout(flagSentTimer);
    flagSentTimer = setTimeout(() => {
      flagSent.value = false;
    }, 2500);
  }
}

function goToSectionLabel(label) {
  const wanted = String(label || "").trim();
  const entry = outline.value.find((item) => item.label === wanted);
  if (entry) goToSection(entry);
}

// The heading a node sits under: the last outline entry before it.
function headingBefore(node) {
  let label = "";
  for (let i = 0; i < outlineEls.length; i += 1) {
    const el = outlineEls[i];
    const precedes =
      el === node ||
      el.contains(node) ||
      Boolean(el.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING);
    if (!precedes) break;
    label = outline.value[i]?.label || "";
  }
  return label;
}

// Flag on a text selection in the rendered memo (G7): a small "Flag"
// button over the selection opens the flag form with the quote.
function onSelectionEnd() {
  if (renderedKind.value !== "docx" || !canComment.value || loading.value) {
    flagButton.value = null;
    return;
  }
  const selection = typeof window.getSelection === "function" ? window.getSelection() : null;
  const container = docxContainer.value;
  if (!selection || selection.isCollapsed || !selection.rangeCount || !container) {
    flagButton.value = null;
    return;
  }
  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) {
    flagButton.value = null;
    return;
  }
  const quote = String(selection.toString() || "").replace(/\s+/g, " ").trim();
  if (quote.length < 2) {
    flagButton.value = null;
    return;
  }
  const body = bodyEl.value?.getBoundingClientRect?.() || { left: 0, top: 0 };
  const rect = typeof range.getBoundingClientRect === "function" ? range.getBoundingClientRect() : null;
  const width = bodyEl.value?.clientWidth || 0;
  const x = rect ? rect.left - body.left + rect.width / 2 : 48;
  const y = rect ? rect.top - body.top - 34 : 8;
  flagButton.value = {
    x: width > 96 ? Math.min(Math.max(x, 48), width - 48) : Math.max(x, 48),
    y: Math.max(4, y),
    quote: quote.slice(0, 300),
    label: headingBefore(range.startContainer),
    language: activeLanguage.value,
  };
}

function startFlag() {
  const draft = flagButton.value;
  if (!draft) return;
  flagDraft.value = { quote: draft.quote, label: draft.label, language: draft.language };
  flagButton.value = null;
  sidePanel.value = "comments";
  try {
    window.getSelection?.()?.removeAllRanges?.();
  } catch {
    // nothing selected any more
  }
}

// ---- Print and share ---------------------------------------------------------------

const canPrint = computed(
  () => ["docx", "pdf", "md", "text"].includes(renderedKind.value) && !loading.value && !loadError.value,
);
const linkCopied = ref(false);
const fallbackLink = ref("");
let linkTimer = null;

// The PDF prints itself; the docx render (or a working paper) prints
// through style.css's print rules, which drop everything but the document.
function printDocument() {
  if (renderedKind.value === "pdf") {
    try {
      const frame = pdfFrame.value?.contentWindow;
      if (frame) {
        frame.focus();
        frame.print();
        return;
      }
    } catch {
      // the PDF viewer refused: print the page instead
    }
  }
  const root = document.documentElement;
  root.dataset.bshPrint = "document";
  let timer = null;
  const done = () => {
    clearTimeout(timer);
    window.removeEventListener("afterprint", done);
    if (root.dataset.bshPrint === "document") delete root.dataset.bshPrint;
  };
  window.addEventListener("afterprint", done);
  // The attribute only matters to print media, so a browser that never
  // fires afterprint loses nothing on screen while it lingers.
  timer = setTimeout(done, 60_000);
  window.print();
}

async function copyLink() {
  const id = props.report?.id;
  if (!id) return;
  const key = String(activeSourceObj.value?.key || "").toLowerCase();
  const url = reportShareUrl(id, key || undefined);
  const ok = await copyText(url);
  clearTimeout(linkTimer);
  if (ok) {
    fallbackLink.value = "";
    linkCopied.value = true;
    linkTimer = setTimeout(() => {
      linkCopied.value = false;
    }, 2000);
  } else {
    fallbackLink.value = url;
  }
}

// ---- Review moves (G2) ---------------------------------------------------------

const reviewMoves = computed(() => (props.report ? reviewActions(props.report, permissionList.value) : []));
const reviewBusy = ref("");
const reviewError = ref("");
const reviewErrorDetail = ref("");
// A move the server held back: open comments/flags (acknowledge to go on)
// or ink on the document (force the re-stamp).
const reviewPrompt = ref(null); // { state, kind: "open_items" | "ink", count }

function errorDetail(error) {
  const detail = error?.detail;
  if (detail && typeof detail === "object" && typeof detail.detail === "string") return detail.detail;
  if (typeof detail === "string") return detail;
  return String(error?.message || "");
}

async function runReview(state, { acknowledge = false, force = false } = {}) {
  const id = props.report?.id;
  if (!id || reviewBusy.value) return;
  reviewBusy.value = state;
  reviewError.value = "";
  reviewErrorDetail.value = "";
  reviewPrompt.value = null;
  try {
    await api.setReportReview(id, {
      state,
      ...(acknowledge ? { acknowledgeOpenComments: true } : {}),
      ...(force ? { force: true } : {}),
    });
    emit("report-changed", { action: "review", id, state });
  } catch (error) {
    const detail = errorDetail(error);
    const status = Number(error?.status);
    if ((status === 409 || status === 400) && /open comment|flag/i.test(detail)) {
      const counted = Number(detail.match(/(\d+)\s+open/i)?.[1]);
      reviewPrompt.value = {
        state,
        kind: "open_items",
        count: Number.isFinite(counted) && counted > 0 ? counted : openItems.value,
        force,
      };
    } else if (status === 409 && /\bink\b/i.test(detail)) {
      reviewPrompt.value = { state, kind: "ink", acknowledge };
    } else {
      reviewError.value = t("review.failed");
      reviewErrorDetail.value = detail;
    }
  } finally {
    reviewBusy.value = "";
  }
}

function confirmReviewPrompt() {
  const prompt = reviewPrompt.value;
  if (!prompt) return;
  runReview(prompt.state, {
    acknowledge: prompt.kind === "open_items" || Boolean(prompt.acknowledge),
    force: prompt.kind === "ink" || Boolean(prompt.force),
  });
}

watch(
  () => props.report?.id,
  () => {
    flagDraft.value = null;
    flagButton.value = null;
    reviewPrompt.value = null;
    reviewError.value = "";
    fallbackLink.value = "";
    linkCopied.value = false;
    if (sidePanel.value === "changes" && !canCompare.value) sidePanel.value = "";
  },
);

// ---- Lifecycle ----------------------------------------------------------------

const sourcesSignature = computed(() =>
  props.sources.map((s) => `${s.key}|${s.url}|${s.kind}`).join("\n"),
);

watch(sourcesSignature, () => {
  activeIndex.value = resolveInitialIndex();
  pendingPosition = null;
  pendingSection = props.initialSection;
  papersOpen.value = false;
  loadSource();
});

watch(
  () => activePaperObj.value?.filename || "",
  () => loadSource(),
);

// Moving between the page and full screen changes the width, so the page is
// refitted; keep the reader where they were.
watch(
  () => props.fullscreen,
  () => {
    const position = capturePosition();
    if (!position) return;
    nextTick()
      .then(nextFrame)
      .then(nextFrame)
      .then(() => restorePosition(position));
  },
  { flush: "pre" },
);

function onKeydown(event) {
  if (event.key === "Escape" && papersOpen.value) {
    // Escape closes the menu only, not full screen behind it.
    event.stopPropagation();
    papersOpen.value = false;
  } else if (event.key === "Escape" && flagButton.value) {
    flagButton.value = null;
  }
}

onMounted(() => {
  activeIndex.value = resolveInitialIndex();
  pendingSection = props.initialSection;
  loadSource();
  // Refit when the viewer changes width: the window, or the reports list
  // hiding and coming back beside it.
  if (typeof ResizeObserver !== "undefined" && scrollArea.value) {
    resizeObserver = new ResizeObserver(() => {
      fitDocx();
      if (bodyEl.value) bodyWidth.value = bodyEl.value.clientWidth;
    });
    resizeObserver.observe(scrollArea.value);
    if (bodyEl.value) resizeObserver.observe(bodyEl.value);
  }
  if (bodyEl.value) bodyWidth.value = bodyEl.value.clientWidth;
  document.addEventListener("pointerdown", onDocPointerDown);
  document.addEventListener("keydown", onKeydown);
  // A selection often ends with the pointer outside the page it started on.
  document.addEventListener("mouseup", onSelectionEnd);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  document.removeEventListener("pointerdown", onDocPointerDown);
  document.removeEventListener("keydown", onKeydown);
  document.removeEventListener("mouseup", onSelectionEnd);
  clearTimeout(flagSentTimer);
  clearTimeout(linkTimer);
});
</script>

<template>
  <div class="flex h-full w-full flex-col overflow-hidden bg-surface">
    <!-- One slim bar, so the document gets the height: what it is on the
         left, its controls on the right. On a phone the controls wrap to a
         second line rather than squeeze the title out. -->
    <header class="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-subtle bg-surface px-3 py-1.5">
      <div class="flex min-w-0 flex-1 basis-[14rem] items-center gap-2">
        <button
          v-if="showBack"
          type="button"
          class="icon-btn !h-7 !w-7 shrink-0"
          :aria-label="t('reports.back_to_list')"
          :title="t('reports.back_to_list')"
          data-testid="viewer-back"
          @click="emit('back')"
        >
          <ArrowLeft class="h-4 w-4" />
        </button>
        <Monogram
          v-if="companyId || companyName"
          :company="headerCompany"
          :size="20"
          tinted
          class="shrink-0"
          data-testid="viewer-logo"
        />
        <FileText v-else class="h-4 w-4 shrink-0 text-accent" />
        <h2 class="min-w-0 truncate text-sm font-semibold text-ink-primary" :title="title">
          {{ title || t("reports.viewer_window_title") }}
        </h2>
        <span
          v-if="icTemplate"
          class="chip shrink-0 bg-accent-soft text-accent-ink max-md:hidden"
          :title="t('reports.ic_template_tag_hint')"
          data-testid="viewer-ic-template"
        >
          {{ t("reports.ic_template_tag") }}
        </span>
        <RouterLink
          v-if="companyId && companyLinkable"
          :to="{ name: 'research', params: { companyId } }"
          class="flex min-w-0 shrink items-center gap-1 text-xs font-medium text-accent hover:underline"
          :title="companyLinkTitle"
          :aria-label="companyLinkTitle"
          data-testid="viewer-company-link"
        >
          <span v-if="!titleNamesCompany" class="truncate">{{ companyName || companyId }}</span>
          <ExternalLink class="h-3 w-3 shrink-0" />
        </RouterLink>
        <span
          v-else-if="companyName && !titleNamesCompany"
          class="min-w-0 truncate text-xs font-medium text-ink-secondary"
          data-testid="viewer-company-name"
        >
          {{ companyName }}
        </span>
        <span
          v-if="date && !compactHeader && !showMeta"
          class="shrink-0 whitespace-nowrap text-xs text-ink-muted tabular max-md:hidden"
        >
          · {{ date }}
        </span>
      </div>

      <!-- Controls: outline, language, working papers, zoom, export, full screen -->
      <div class="ml-auto flex shrink-0 items-center gap-1.5">
        <button
          v-if="outlineAvailable"
          type="button"
          class="rounded-full p-1.5 transition-colors focus-ring"
          :class="outlineVisible ? 'bg-accent text-white shadow-xs' : 'text-ink-muted hover:bg-surface-muted hover:text-ink-primary'"
          :aria-pressed="outlineVisible"
          :title="outlineVisible ? t('reports.outline_hide') : t('reports.outline_show')"
          :aria-label="outlineVisible ? t('reports.outline_hide') : t('reports.outline_show')"
          data-testid="viewer-outline-toggle"
          @click="toggleOutline"
        >
          <TableOfContents class="h-3.5 w-3.5" />
        </button>

        <button
          v-if="activePaperObj"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface-muted px-2.5 py-0.5 text-[11px] font-semibold text-ink-secondary transition-colors hover:text-ink-primary focus-ring"
          data-testid="viewer-paper-back"
          @click="choosePaper(null)"
        >
          <ArrowLeft class="h-3 w-3" />
          {{ t("reports.papers_back") }}
        </button>
        <div
          v-else-if="sources.length > 1"
          class="flex items-center gap-1 rounded-full border border-subtle bg-surface-muted p-0.5"
        >
          <button
            v-for="(source, index) in sources"
            :key="source.key"
            type="button"
            class="relative rounded-full px-2.5 py-0.5 text-[11px] font-semibold transition-colors focus-ring"
            :class="
              index === activeIndex
                ? 'bg-accent text-white shadow-xs'
                : 'text-ink-secondary hover:text-ink-primary'
            "
            :title="warningKeys.includes(source.key) ? t('reports.warning_dot') : source.hint || null"
            :aria-pressed="index === activeIndex"
            :data-testid="`viewer-source-${String(source.key).toLowerCase()}`"
            @click="selectSource(index)"
          >
            {{ source.label || source.key }}
            <span
              v-if="warningKeys.includes(source.key)"
              class="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-warning ring-2 ring-surface"
              aria-hidden="true"
              data-testid="viewer-warning-dot"
            ></span>
          </button>
        </div>

        <div v-if="papers.length" ref="papersMenu" class="relative">
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold transition-colors focus-ring"
            :class="
              activePaperObj || papersOpen
                ? 'border-accent bg-accent-soft text-accent-ink'
                : 'border-subtle bg-surface-muted text-ink-secondary hover:text-ink-primary'
            "
            :aria-expanded="papersOpen"
            aria-haspopup="menu"
            :title="t('reports.papers_hint')"
            data-testid="viewer-papers"
            @click="papersOpen = !papersOpen"
          >
            <NotebookText class="h-3 w-3" />
            <span v-if="!compactHeader" class="max-sm:hidden">{{ t("reports.papers") }}</span>
          </button>
          <div
            v-if="papersOpen"
            class="glass-panel glass-popover absolute right-0 top-full z-30 mt-1.5 w-72 max-w-[85vw] rounded-[13px] p-1.5"
            role="menu"
            data-testid="viewer-papers-menu"
          >
            <div class="px-2 pb-1.5 pt-1">
              <div class="text-footnote font-semibold text-ink-primary">{{ t("reports.papers") }}</div>
              <div class="text-caption1 text-ink-muted">{{ t("reports.papers_hint") }}</div>
              <div v-if="appLanguage === 'zh'" class="mt-0.5 text-caption1 text-ink-muted">
                {{ t("reports.papers_english_only") }}
              </div>
            </div>
            <div class="max-h-72 overflow-y-auto">
              <button
                v-for="paper in papers"
                :key="paper.filename"
                type="button"
                role="menuitem"
                class="flex w-full flex-col items-stretch rounded-[8px] px-2 py-1.5 text-left transition-colors hover:bg-ink-primary/[0.05] focus-ring"
                :class="paper.filename === activePaper ? 'bg-accent/10' : ''"
                :data-testid="`viewer-paper-${paper.filename}`"
                @click="choosePaper(paper)"
              >
                <span
                  class="truncate text-footnote"
                  :class="paper.filename === activePaper ? 'font-semibold text-accent-ink' : 'text-ink-primary'"
                >
                  {{ paper.label || paper.filename }}
                </span>
                <span v-if="paperDidNotRun(paper)" class="text-caption2 text-ink-muted">
                  {{ t("reports.paper_not_run") }}
                </span>
              </button>
            </div>
          </div>
        </div>

        <!-- PDF (paginated, as it prints) or the web render (outline, zoom, flags). -->
        <div
          v-if="offersPdf"
          class="flex items-center gap-0.5 rounded-full border border-subtle bg-surface-muted p-0.5"
          role="group"
          :aria-label="t('viewer.mode_label')"
          data-testid="viewer-mode"
        >
          <button
            type="button"
            class="rounded-full px-2 py-0.5 text-[11px] font-semibold transition-colors focus-ring"
            :class="renderedKind === 'pdf' ? 'bg-accent text-white shadow-xs' : 'text-ink-secondary hover:text-ink-primary'"
            :aria-pressed="renderedKind === 'pdf'"
            :title="t('viewer.mode_pdf_hint')"
            data-testid="viewer-mode-pdf"
            @click="setViewMode('pdf')"
          >
            {{ t("viewer.mode_pdf") }}
          </button>
          <button
            type="button"
            class="rounded-full px-2 py-0.5 text-[11px] font-semibold transition-colors focus-ring"
            :class="renderedKind !== 'pdf' ? 'bg-accent text-white shadow-xs' : 'text-ink-secondary hover:text-ink-primary'"
            :aria-pressed="renderedKind !== 'pdf'"
            :title="t('viewer.mode_web_hint')"
            data-testid="viewer-mode-web"
            @click="setViewMode('web')"
          >
            {{ t("viewer.mode_web") }}
          </button>
        </div>

        <div
          v-if="renderedKind === 'docx' && !loading && !loadError"
          class="flex items-center gap-0.5 rounded-full border border-subtle bg-surface-muted p-0.5 max-sm:hidden"
          role="group"
          :aria-label="t('documents.zoom')"
          data-testid="viewer-zoom"
        >
          <button
            type="button"
            class="rounded-full p-1 text-ink-secondary transition-colors hover:text-ink-primary disabled:opacity-40 focus-ring"
            :disabled="docxZoom <= ZOOM_MIN"
            :title="t('documents.zoom_out')"
            :aria-label="t('documents.zoom_out')"
            data-testid="viewer-zoom-out"
            @click="zoomOut"
          >
            <ZoomOut class="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            class="min-w-[2.75rem] rounded-full px-1 py-0.5 text-[11px] font-semibold text-ink-secondary tabular transition-colors hover:text-ink-primary focus-ring"
            :title="t('documents.zoom_actual')"
            data-testid="viewer-zoom-level"
            @click="setZoom(1)"
          >
            {{ zoomPercent }}
          </button>
          <button
            type="button"
            class="rounded-full p-1 text-ink-secondary transition-colors hover:text-ink-primary disabled:opacity-40 focus-ring"
            :disabled="docxZoom >= ZOOM_MAX"
            :title="t('documents.zoom_in')"
            :aria-label="t('documents.zoom_in')"
            data-testid="viewer-zoom-in"
            @click="zoomIn"
          >
            <ZoomIn class="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            class="rounded-full p-1 transition-colors focus-ring"
            :class="isFit ? 'bg-accent text-white shadow-xs' : 'text-ink-secondary hover:text-ink-primary'"
            :aria-pressed="isFit"
            :title="t('documents.zoom_fit')"
            :aria-label="t('documents.zoom_fit')"
            data-testid="viewer-zoom-fit"
            @click="setZoom('fit')"
          >
            <MoveHorizontal class="h-3.5 w-3.5" />
          </button>
        </div>

        <!-- A memo exports through the menu (PDF / Word / .zip); a working
             paper or a plain document downloads as itself. -->
        <ReportExportMenu
          v-if="isMemo && !activePaperObj && exportOptions.length"
          :options="exportOptions"
          :compact="compactHeader"
          @select="onExportSelect"
        />
        <a
          v-else-if="exportHref && (activePaperObj || !isMemo)"
          :href="exportHref"
          :download="activePaperObj ? activePaperObj.filename : null"
          class="inline-flex items-center gap-1.5 rounded border border-subtle bg-surface px-2.5 py-1 text-xs font-medium text-ink-secondary hover:bg-surface-muted hover:text-ink-primary focus-ring"
          :title="t('documents.export')"
          data-testid="viewer-export"
          @click="onPaperExport"
        >
          <Download class="h-3.5 w-3.5" />
          <span class="max-sm:hidden">{{ t("documents.export") }}</span>
        </a>

        <ReportMoreMenu
          v-if="isMemo && (sources.length > 0 || reviewMoves.length)"
          :can-print="canPrint"
          :can-copy-link="Boolean(report?.id) && sources.length > 0"
          :link-copied="linkCopied"
          :fallback-link="fallbackLink"
          :review-moves="reviewMoves"
          :busy="reviewBusy"
          @print="printDocument"
          @copy-link="copyLink"
          @review="runReview"
        />

        <button
          v-if="sources.length > 0 || report"
          type="button"
          class="inline-flex items-center gap-1 rounded border border-subtle bg-surface p-1.5 text-xs text-ink-muted hover:bg-surface-muted hover:text-ink-primary focus-ring"
          :title="fullscreen ? t('reports.exit_fullscreen') : t('reports.open_in_drawer')"
          :aria-label="fullscreen ? t('reports.exit_fullscreen') : t('reports.open_in_drawer')"
          :aria-pressed="fullscreen"
          data-testid="viewer-fullscreen"
          @click="onFullscreen"
        >
          <Minimize2 v-if="fullscreen" class="h-3.5 w-3.5" />
          <Maximize2 v-else class="h-3.5 w-3.5" />
        </button>

        <button
          v-if="allowClose"
          type="button"
          class="rounded-full p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink-primary focus-ring"
          :title="t('documents.viewer_close')"
          @click="emit('close')"
        >
          <X class="h-4 w-4" />
        </button>
      </div>
    </header>

    <!-- What the memo concludes, its review, whether it is current — and the
         comments and "changes since" panels. -->
    <div
      v-if="showMeta"
      class="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-b border-subtle bg-surface px-3 py-1"
      data-testid="viewer-meta"
    >
      <span
        v-if="verdict"
        class="chip shrink-0"
        :class="toneClasses(verdict.tone)"
        :title="verdict.title"
        data-testid="viewer-verdict"
      >
        {{ verdict.label }}
      </span>
      <span
        v-if="review"
        class="chip shrink-0"
        :class="toneClasses(review.tone)"
        :title="review.title"
        data-testid="viewer-review"
      >
        {{ review.label }}
      </span>
      <span
        v-if="renderNote"
        class="inline-flex shrink-0 items-center gap-1 text-caption1 font-medium text-warning-ink"
        :title="renderNote"
        data-testid="viewer-review-render"
      >
        <TriangleAlert class="h-3 w-3" />
        {{ t("review.render.label") }}
      </span>
      <span
        v-if="freshness"
        class="min-w-0 truncate text-caption1 tabular"
        :class="freshness.stale ? 'font-medium text-warning-ink' : 'text-ink-muted'"
        :title="freshness.title || null"
        :data-stale="freshness.stale ? 'true' : 'false'"
        data-testid="viewer-freshness"
      >
        {{ freshness.text }}
      </span>
      <span
        v-if="changedFrom"
        class="chip shrink-0 bg-warning-soft text-warning-ink"
        :title="
          version.unstable
            ? t('reports.version.unstable_hint', { span: flipSpan })
            : t('reports.version.changed_from_hint', { verdict: changedFrom })
        "
        :data-unstable="version.unstable ? 'true' : null"
        data-testid="viewer-changed-from"
      >
        <TriangleAlert v-if="version.unstable" class="h-3 w-3" />
        {{
          version.unstable
            ? t("reports.version.unstable_was", { verdict: changedFrom })
            : t("reports.version.changed_from", { verdict: changedFrom })
        }}
      </span>
      <span
        v-if="qualityMetrics"
        class="inline-flex min-w-0 flex-wrap items-center gap-x-1.5 text-caption1 text-ink-muted"
        data-testid="viewer-quality-metrics"
      >
        <span class="font-medium text-ink-secondary">{{ t("reports.quality_metrics.label") }}</span>
        <span
          v-for="item in qualityMetrics"
          :key="item.key"
          class="tabular"
          :title="item.title"
          data-testid="viewer-quality-metric"
        >{{ item.label }}</span>
      </span>
      <!-- The panels' toggles keep to the right edge, wrapped or not. -->
      <div class="ml-auto flex shrink-0 items-center gap-1">
        <button
          v-if="canCompare"
          type="button"
          class="inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-caption1 font-medium transition-colors focus-ring"
          :class="sidePanel === 'changes' ? 'bg-accent-soft text-accent-ink' : 'text-ink-secondary hover:bg-ink-primary/[0.05] hover:text-ink-primary'"
          :aria-pressed="sidePanel === 'changes'"
          :title="changesLabel"
          :aria-label="changesLabel"
          data-testid="viewer-changes-toggle"
          @click="togglePanel('changes')"
        >
          <History class="h-3 w-3" />
          <span v-if="!compactHeader">{{ changesLabel }}</span>
        </button>
        <button
          type="button"
          class="inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-caption1 font-medium transition-colors focus-ring"
          :class="sidePanel === 'comments' ? 'bg-accent-soft text-accent-ink' : 'text-ink-secondary hover:bg-ink-primary/[0.05] hover:text-ink-primary'"
          :aria-pressed="sidePanel === 'comments'"
          :title="t('comments.button_hint')"
          :aria-label="t('comments.button_hint')"
          data-testid="viewer-comments-toggle"
          @click="togglePanel('comments')"
        >
          <MessageSquare class="h-3 w-3" />
          <span v-if="!compactHeader">{{ t("comments.button") }}</span>
          <span
            v-if="openItems"
            class="rounded-full bg-warning px-1.5 text-caption2 font-semibold text-white tabular"
            data-testid="viewer-comments-count"
          >{{ openItems }}</span>
        </button>
      </div>
    </div>

    <!-- A review move the server held back, or one that failed. -->
    <div
      v-if="reviewPrompt || reviewError"
      class="flex shrink-0 flex-wrap items-center gap-2 border-b border-subtle bg-warning-soft px-3 py-1.5 text-footnote"
      role="alert"
      data-testid="viewer-review-prompt"
    >
      <TriangleAlert class="h-3.5 w-3.5 shrink-0 text-warning-ink" />
      <span class="min-w-0 flex-1 text-ink-primary" :title="reviewErrorDetail || null">
        <template v-if="reviewPrompt?.kind === 'open_items'">{{ t("review.open_items", { count: reviewPrompt.count }) }}</template>
        <template v-else-if="reviewPrompt?.kind === 'ink'">{{ t("review.ink") }}</template>
        <template v-else>{{ reviewError }}</template>
      </span>
      <button
        v-if="reviewPrompt"
        type="button"
        class="btn-filled btn-sm shrink-0 focus-ring"
        :disabled="Boolean(reviewBusy)"
        data-testid="viewer-review-confirm"
        @click="confirmReviewPrompt"
      >
        {{ reviewPrompt.kind === "ink" ? t("review.restamp_anyway") : t("review.approve_anyway") }}
      </button>
      <button
        type="button"
        class="btn-plain btn-sm shrink-0 focus-ring"
        data-testid="viewer-review-dismiss"
        @click="reviewPrompt = null; reviewError = ''"
      >
        {{ t("review.not_now") }}
      </button>
    </div>

    <!-- Paused after the English memo: read it here, continue from here. -->
    <div
      v-if="pausedStrip"
      class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-subtle bg-notice-soft px-3 py-1.5 text-footnote"
      role="status"
      data-testid="viewer-paused"
    >
      <CirclePause class="h-3.5 w-3.5 shrink-0 text-notice-ink" />
      <div class="min-w-0 flex-1">
        <span class="font-semibold text-notice-ink">{{ t("reports.status_card.paused_title") }}</span>
        <span class="text-ink-secondary"> · {{ t("reports.status_card.paused_body") }}</span>
        <span
          v-if="qualityMetrics"
          class="ml-2 inline-flex flex-wrap items-center gap-x-1.5 text-caption1 text-ink-muted"
          data-testid="viewer-quality-metrics"
        >
          <span class="font-medium text-ink-secondary">{{ t("reports.quality_metrics.label") }}</span>
          <span
            v-for="item in qualityMetrics"
            :key="item.key"
            class="tabular"
            :title="item.title"
            data-testid="viewer-quality-metric"
          >{{ item.label }}</span>
        </span>
      </div>
      <button
        v-if="logJob"
        type="button"
        class="btn-bordered btn-sm focus-ring shrink-0"
        data-testid="viewer-paused-log"
        @click="openLog"
      >
        {{ t("jobs.open_transcript") }}
      </button>
      <button
        type="button"
        class="btn-filled btn-sm focus-ring shrink-0"
        :disabled="Boolean(actionBusy)"
        data-testid="viewer-status-resume"
        @click="runAction('resume')"
      >
        {{ actionLabel("resume") }}
      </button>
      <p v-if="actionError" class="w-full text-caption1 text-danger" role="alert">{{ actionError }}</p>
    </div>

    <!-- What a delivered memo was flagged for: gate, language, section. -->
    <div
      v-if="showWarnings"
      class="flex shrink-0 items-start gap-2 border-b border-subtle bg-warning-soft px-3 py-1.5 text-footnote"
      role="status"
      data-testid="viewer-warnings"
    >
      <TriangleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning-ink" />
      <div class="min-w-0 flex-1">
        <span class="font-semibold text-warning-ink">{{ t("research.complete_with_warnings_title") }}</span>
        <ul class="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-ink-secondary">
          <li
            v-for="(item, index) in visibleWarnings"
            :key="`${item.gate}-${item.language}-${item.section}-${item.code}-${index}`"
            class="min-w-0"
            :title="item.code || item.summary || null"
            data-testid="viewer-warning-item"
          >
            <span class="font-medium text-ink-primary">{{ item.gateLabel }}</span>
            <template v-if="item.language"> · {{ languageName(item.language) }}</template>
            · {{ item.section || item.summary || t("reports.warning_whole_document") }}
            <span
              v-if="item.severity"
              class="ml-1 rounded-[4px] bg-warning/15 px-1 text-caption2 font-semibold text-warning-ink"
            >{{ item.severity }}</span>
          </li>
          <li v-if="warningItems.length > visibleWarnings.length" class="text-ink-muted">
            {{ t("reports.warning_more", { count: warningItems.length - visibleWarnings.length }) }}
          </li>
        </ul>
      </div>
      <button
        type="button"
        class="shrink-0 rounded-full p-1 text-ink-muted transition-colors hover:bg-ink-primary/[0.06] hover:text-ink-primary focus-ring"
        :title="t('reports.warning_hide')"
        :aria-label="t('reports.warning_hide')"
        data-testid="viewer-warnings-hide"
        @click="hideWarnings"
      >
        <X class="h-3.5 w-3.5" />
      </button>
    </div>

    <div ref="bodyEl" class="relative flex min-h-0 flex-1">
      <!-- Outline: beside the page on wide viewers, over it on a phone. -->
      <nav
        v-if="outlineVisible"
        class="doc-viewer-outline z-20 flex w-56 shrink-0 flex-col overflow-y-auto border-r border-subtle bg-surface py-2 max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:shadow-card-raised"
        :aria-label="t('reports.outline')"
        data-testid="viewer-outline"
      >
        <div class="px-3 pb-1.5 text-caption1 font-semibold text-ink-muted">{{ t("reports.outline") }}</div>
        <button
          v-for="entry in outline"
          :key="entry.key"
          type="button"
          class="mx-1.5 rounded-[7px] px-2 py-1 text-left text-footnote leading-snug transition-colors focus-ring"
          :class="[
            entry.level > 1 ? 'pl-5' : '',
            activeSection === entry.key
              ? 'bg-accent/10 font-semibold text-accent-ink'
              : 'text-ink-secondary hover:bg-ink-primary/[0.05] hover:text-ink-primary',
          ]"
          :aria-current="activeSection === entry.key ? 'location' : undefined"
          :data-testid="`viewer-outline-${entry.key}`"
          @click="goToSection(entry)"
        >
          {{ entry.label }}
        </button>
      </nav>

      <!-- Document Content Area -->
      <div
        ref="scrollArea"
        class="relative min-w-0 flex-1 overflow-auto bg-surface-muted/30"
        :class="renderedKind === 'pdf' && !loading ? 'p-0' : 'p-3'"
        data-testid="viewer-scroll"
        @wheel="onWheel"
        @scroll="onScroll"
        @click="onContentClick"
        @keyup="onSelectionEnd"
      >
        <div
          v-if="loading"
          class="flex h-full min-h-[300px] flex-col items-center justify-center gap-2 text-sm text-ink-muted"
        >
          <Loader2 class="h-6 w-6 animate-spin text-accent" />
          <span>{{ t("documents.viewer_loading") }}</span>
        </div>

        <div
          v-else-if="loadError"
          class="flex h-full min-h-[300px] flex-col items-center justify-center gap-3 p-6 text-center"
        >
          <div class="rounded-full bg-danger/10 p-3 text-danger">
            <FileText class="h-6 w-6" />
          </div>
          <div>
            <div class="font-medium text-ink-primary">{{ t("documents.viewer_error") }}</div>
            <p class="mt-1 text-xs text-ink-muted max-w-sm">
              {{ t("research.pdf_preview_unavailable_hint") }}
            </p>
          </div>
          <button
            type="button"
            class="inline-flex items-center gap-1.5 rounded-md border border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-ink-primary hover:bg-surface-muted focus-ring"
            @click="loadSource()"
          >
            <RefreshCw class="h-3.5 w-3.5" />
            <span>{{ t("research.retry") }}</span>
          </button>
        </div>

        <!-- No document: the run's status, not an empty page. -->
        <div
          v-else-if="statusKind"
          class="flex h-full min-h-[300px] items-start justify-center p-4 sm:items-center"
        >
          <div
            class="w-full max-w-lg rounded-card border border-subtle bg-surface p-5 shadow-xs"
            data-testid="viewer-status"
            :data-state="statusKind"
          >
            <div class="flex items-start gap-3">
              <span
                class="grid h-9 w-9 shrink-0 place-items-center rounded-full"
                :class="{
                  'bg-info-soft text-info-ink': statusKind === 'running',
                  'bg-danger-soft text-danger-ink': statusKind === 'failed',
                  'bg-accent-soft text-accent-ink': statusKind === 'cards_ready',
                  'bg-notice-soft text-notice-ink': statusKind === 'paused',
                  'bg-fill-tertiary text-ink-muted': statusKind === 'docless',
                }"
              >
                <Loader2 v-if="statusKind === 'running'" class="h-4 w-4 animate-spin" />
                <CircleAlert v-else-if="statusKind === 'failed'" class="h-4 w-4" />
                <Sparkles v-else-if="statusKind === 'cards_ready'" class="h-4 w-4" />
                <CirclePause v-else-if="statusKind === 'paused'" class="h-4 w-4" />
                <FileWarning v-else class="h-4 w-4" />
              </span>
              <div class="min-w-0 flex-1">
                <h3 class="text-callout font-semibold text-ink-primary" data-testid="viewer-status-title">
                  {{ statusTitle }}
                </h3>

                <template v-if="statusKind === 'running'">
                  <p class="mt-1 text-footnote text-ink-secondary">{{ t("reports.status_card.running_body") }}</p>
                  <p v-if="runningStage" class="mt-2 text-footnote text-ink-primary">
                    {{ t("reports.status_card.stage", { stage: runningStage }) }}
                  </p>
                  <div v-if="runningProgress != null" class="mt-2">
                    <div class="h-1 w-full overflow-hidden rounded-full bg-ink-primary/[0.08]">
                      <div class="progress-fill h-full rounded-full transition-all" :style="{ width: `${runningProgress}%` }"></div>
                    </div>
                    <div class="mt-1 flex gap-2 text-caption1 text-ink-muted tabular">
                      <span>{{ t("reports.status_card.progress", { pct: runningProgress }) }}</span>
                      <span v-if="runningElapsed">{{ runningElapsed }}</span>
                    </div>
                  </div>
                </template>

                <template v-else-if="statusKind === 'failed'">
                  <p v-if="failureSummary" class="mt-1 text-footnote text-ink-primary" data-testid="viewer-status-summary">
                    {{ failureSummary }}
                  </p>
                  <p v-if="failureStage" class="mt-1 text-footnote text-ink-secondary">{{ failureStage }}</p>
                  <p v-if="failureDetail" class="mt-1 whitespace-pre-wrap break-words text-footnote text-ink-secondary" data-testid="viewer-status-detail">
                    {{ failureDetail }}
                  </p>
                  <p v-else-if="!failureStage && !failureSummary" class="mt-1 text-footnote text-ink-secondary">
                    {{ t("reports.status_card.failed_body") }}
                  </p>
                  <p v-if="failureSpend" class="mt-2 text-caption1 text-ink-muted tabular" data-testid="viewer-status-spend">
                    {{ t("reports.status_card.spend", { amount: failureSpend }) }}
                  </p>
                  <p v-if="failedAtLabel" class="mt-2 text-caption1 text-ink-muted">
                    {{
                      report?.dismissed_at
                        ? t("reports.status_card.failed_at", { time: failedAtLabel })
                        : t("research.failed_run_at", { time: failedAtLabel })
                    }}
                  </p>
                  <p v-if="report?.superseded_by" class="mt-1 text-caption1 text-ink-muted">
                    {{ t("research.failed_run_superseded") }}
                  </p>
                  <p v-if="report?.dismissed_at" class="mt-1 text-caption1 text-ink-muted">
                    {{ t("reports.status_card.dismissed_note") }}
                  </p>
                </template>

                <p v-else-if="statusKind === 'cards_ready'" class="mt-1 text-footnote text-ink-secondary">
                  {{ t("reports.status_card.cards_ready_body") }}
                </p>

                <template v-else-if="statusKind === 'paused'">
                  <p class="mt-1 text-footnote text-ink-secondary">{{ t("reports.status_card.paused_body") }}</p>
                  <p v-if="runningStage" class="mt-2 text-footnote text-ink-primary">
                    {{ t("reports.status_card.stage", { stage: runningStage }) }}
                  </p>
                </template>

                <p v-else class="mt-1 text-footnote text-ink-secondary">{{ doclessBody }}</p>

                <p
                  v-if="qualityMetrics"
                  class="mt-2 flex flex-wrap items-center gap-x-1.5 text-caption1 text-ink-muted"
                  data-testid="viewer-quality-metrics"
                >
                  <span class="font-medium text-ink-secondary">{{ t("reports.quality_metrics.label") }}</span>
                  <span
                    v-for="item in qualityMetrics"
                    :key="item.key"
                    class="tabular"
                    :title="item.title"
                    data-testid="viewer-quality-metric"
                  >{{ item.label }}</span>
                </p>

                <div class="mt-4 flex flex-wrap items-center gap-2">
                  <template v-if="statusKind === 'running'">
                    <button
                      v-if="logJob"
                      type="button"
                      class="btn-bordered btn-sm focus-ring"
                      data-testid="viewer-status-log"
                      @click="openLog"
                    >
                      {{ t("jobs.open_transcript") }}
                    </button>
                    <button
                      type="button"
                      class="btn-bordered btn-sm focus-ring"
                      :class="arm.armed.value === 'cancel' ? '!text-danger' : ''"
                      :disabled="Boolean(actionBusy)"
                      data-testid="viewer-status-cancel"
                      @click="runAction('cancel')"
                    >
                      {{ actionLabel("cancel") }}
                    </button>
                  </template>
                  <template v-else-if="statusKind === 'failed'">
                    <button
                      v-if="report?.resume_available"
                      type="button"
                      class="btn-filled btn-sm focus-ring"
                      :disabled="Boolean(actionBusy)"
                      data-testid="viewer-status-resume"
                      @click="runAction('resume')"
                    >
                      {{ actionLabel("resume") }}
                    </button>
                    <button
                      v-if="!report?.dismissed_at"
                      type="button"
                      class="btn-bordered btn-sm focus-ring"
                      :class="arm.armed.value === 'dismiss' ? '!text-danger' : ''"
                      :disabled="Boolean(actionBusy)"
                      data-testid="viewer-status-dismiss"
                      @click="runAction('dismiss')"
                    >
                      {{ actionLabel("dismiss") }}
                    </button>
                    <button
                      v-if="openReportCustomizer"
                      type="button"
                      class="btn-plain btn-sm focus-ring"
                      data-testid="viewer-status-new"
                      @click="newReport"
                    >
                      {{ t("memo.generate_report") }}
                    </button>
                  </template>
                  <template v-else-if="statusKind === 'paused'">
                    <button
                      type="button"
                      class="btn-filled btn-sm focus-ring"
                      :disabled="Boolean(actionBusy)"
                      data-testid="viewer-status-resume"
                      @click="runAction('resume')"
                    >
                      {{ actionLabel("resume") }}
                    </button>
                    <button
                      v-if="logJob"
                      type="button"
                      class="btn-bordered btn-sm focus-ring"
                      data-testid="viewer-status-log"
                      @click="openLog"
                    >
                      {{ t("jobs.open_transcript") }}
                    </button>
                  </template>
                  <RouterLink
                    v-else-if="statusKind === 'cards_ready' && companyId && companyLinkable"
                    :to="{ name: 'research', params: { companyId }, query: { section: 'memos' } }"
                    class="btn-bordered btn-sm focus-ring"
                  >
                    {{ t("reports.open_report") }}
                  </RouterLink>
                </div>
                <p v-if="actionError" class="mt-2 text-caption1 text-danger" role="alert">{{ actionError }}</p>
              </div>
            </div>
          </div>
        </div>

        <div
          v-else-if="!sources.length"
          class="flex h-full min-h-[300px] flex-col items-center justify-center p-6 text-center text-ink-muted"
        >
          <FileText class="h-8 w-8 text-ink-subtle mb-2" />
          <div class="text-sm font-medium text-ink-secondary">{{ t("reports.select_prompt") }}</div>
          <p class="mt-1 text-xs text-ink-muted max-w-md">{{ t("reports.select_prompt_desc") }}</p>
        </div>

        <div
          v-show="renderedKind === 'docx' && !loading && !loadError"
          ref="docxContainer"
          class="doc-viewer-docx doc-print-target"
          :style="{ zoom: docxZoom }"
          data-testid="viewer-docx"
        ></div>

        <!-- The memo's PDF, rendered by the browser (only when it is ready). -->
        <iframe
          v-if="renderedKind === 'pdf' && pdfSrc"
          ref="pdfFrame"
          :src="pdfSrc"
          class="block h-full min-h-[300px] w-full border-0 bg-surface"
          :title="t('viewer.pdf_title', { title: title || t('documents.viewer_title') })"
          data-testid="viewer-pdf"
          @load="onPdfLoad"
        ></iframe>

        <template v-if="renderedKind === 'md' && !loading && !loadError">
          <p
            v-if="activePaperObj && appLanguage === 'zh'"
            class="mx-auto mb-2 max-w-4xl text-caption1 text-ink-muted"
            data-testid="viewer-paper-english-only"
          >
            {{ t("reports.papers_english_only") }}
          </p>
          <div
            v-if="paperIsPlaceholder"
            class="mx-auto my-2 max-w-4xl rounded-card border border-subtle bg-surface p-6 shadow-xs"
            data-testid="viewer-paper-not-run"
          >
            <div class="text-callout font-semibold text-ink-primary">{{ t("reports.paper_not_run") }}</div>
            <p class="mt-1 text-footnote text-ink-secondary">{{ t("reports.paper_not_run_body") }}</p>
          </div>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div
            v-else
            class="doc-viewer-markdown doc-print-target mx-auto max-w-4xl rounded-card bg-surface p-8 text-sm leading-relaxed text-ink-primary shadow-xs border border-subtle my-2"
            v-html="markdownHtml"
          ></div>
        </template>

        <pre
          v-if="renderedKind === 'text' && !loading && !loadError"
          class="doc-viewer-text doc-print-target mx-auto max-w-4xl whitespace-pre-wrap rounded-card bg-surface p-6 font-mono text-xs leading-relaxed text-ink-primary shadow-xs border border-subtle my-2"
        >{{ textContent }}</pre>
      </div>

      <!-- "Flag" over a text selection in the memo. -->
      <button
        v-if="flagButton"
        type="button"
        class="absolute z-30 inline-flex -translate-x-1/2 items-center gap-1 rounded-full bg-ink-primary px-2.5 py-1 text-caption1 font-semibold text-surface shadow-card-raised focus-ring"
        :style="{ left: `${flagButton.x}px`, top: `${flagButton.y}px` }"
        :title="t('comments.flag_hint')"
        data-testid="viewer-flag-selection"
        @mousedown.prevent
        @click="startFlag"
      >
        <Flag class="h-3 w-3" />
        {{ t("comments.flag") }}
      </button>
      <p
        v-if="flagSent && sidePanel !== 'comments'"
        class="pointer-events-none absolute bottom-3 left-1/2 z-30 -translate-x-1/2 rounded-full bg-ink-primary px-3 py-1 text-caption1 font-medium text-surface shadow-card-raised"
        role="status"
      >
        {{ t("comments.flag_sent") }}
      </p>

      <!-- Comments and flags, or what changed since the previous memo. -->
      <aside
        v-if="sidePanel && report?.id"
        class="z-20 flex w-[22rem] max-w-full shrink-0 flex-col border-l border-subtle bg-surface"
        :class="panelOverlay ? 'absolute inset-y-0 right-0 shadow-card-raised' : ''"
        :aria-label="sidePanel === 'comments' ? t('comments.title') : t('viewer.changes')"
        data-testid="viewer-side-panel"
        :data-panel="sidePanel"
      >
        <ReportCommentsPanel
          v-if="sidePanel === 'comments'"
          :report="report"
          :language="activeLanguage"
          :section="currentSection"
          :flag-draft="flagDraft"
          :can-edit="canComment"
          @close="closePanel"
          @changed="onCommentsChanged"
          @flag-done="onFlagDone"
          @go-to-section="goToSectionLabel"
        />
        <ReportChangesPanel
          v-else-if="sidePanel === 'changes'"
          :report="report"
          :previous="previousVersion"
          :lang="appLanguage"
          @close="closePanel"
        />
      </aside>
    </div>
  </div>
</template>

<style scoped>
/* Zoomed wider than the viewer, the page grows past it to the right and the
   view scrolls sideways; centering it would push its left edge out of reach. */
.doc-viewer-docx :deep(.docx-wrapper) {
  background: transparent;
  padding: 0;
  width: max-content;
  min-width: 100%;
}
.doc-viewer-docx :deep(.docx-wrapper > section.docx) {
  margin: 0 auto 1.5rem;
  box-shadow: 0 2px 8px rgb(0 0 0 / 0.1);
  background: white;
}

.doc-viewer-markdown :deep(h1) {
  font-size: 1.4rem;
  font-weight: 700;
  margin: 1.2rem 0 0.6rem;
}
.doc-viewer-markdown :deep(h2) {
  font-size: 1.15rem;
  font-weight: 700;
  margin: 1.1rem 0 0.5rem;
}
.doc-viewer-markdown :deep(h3) {
  font-size: 1rem;
  font-weight: 600;
  margin: 1rem 0 0.4rem;
}
.doc-viewer-markdown :deep(p) {
  margin: 0.5rem 0;
}
.doc-viewer-markdown :deep(ul),
.doc-viewer-markdown :deep(ol) {
  margin: 0.5rem 0 0.5rem 1.4rem;
  list-style: disc;
}
.doc-viewer-markdown :deep(ol) {
  list-style: decimal;
}
.doc-viewer-markdown :deep(li) {
  margin: 0.2rem 0;
}
/* Working papers carry wide tables; they scroll inside the card rather
   than push it past the viewer. Borders come from the app's tokens, so they
   read in dark mode too. */
.doc-viewer-markdown :deep(table) {
  border-collapse: collapse;
  margin: 0.8rem 0;
  width: 100%;
  display: block;
  overflow-x: auto;
}
.doc-viewer-markdown :deep(th),
.doc-viewer-markdown :deep(td) {
  border: 1px solid rgb(var(--color-border-subtle));
  padding: 0.35rem 0.5rem;
  text-align: left;
  vertical-align: top;
}
.doc-viewer-markdown :deep(th) {
  background: rgb(var(--color-fill-tertiary));
  font-weight: 600;
}
.doc-viewer-markdown :deep(code) {
  background: rgb(var(--color-fill-secondary));
  border-radius: 0.25rem;
  font-size: 0.85em;
  padding: 0.1rem 0.3rem;
}
.doc-viewer-markdown :deep(pre code) {
  display: block;
  overflow-x: auto;
  padding: 0.6rem;
}
.doc-viewer-markdown :deep(blockquote) {
  border-left: 3px solid rgb(var(--color-border-strong));
  color: rgb(var(--color-text-secondary));
  margin: 0.6rem 0;
  padding-left: 0.8rem;
}
.doc-viewer-markdown :deep(a) {
  color: rgb(var(--color-accent-ink));
  text-decoration: underline;
}
</style>
