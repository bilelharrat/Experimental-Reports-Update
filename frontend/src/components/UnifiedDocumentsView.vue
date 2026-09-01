<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from "vue";
import {
  AlertCircle,
  ChevronDown,
  Download,
  Eye,
  FileText,
  Filter,
  Loader2,
  Search,
  Trash2,
  UploadCloud,
} from "lucide-vue-next";
import { api, withApiToken } from "../api.js";
import AiMark from "./AiMark.vue";
import { formatIsoDate, humanizeStatus, isTerminalReportStatus } from "../formatters.js";
import { useT } from "../i18n.js";
import { appLanguage, openSummary } from "../state.js";
import FilePreviewModal from "./FilePreviewModal.vue";

// Lazy: the viewer pulls in docx-preview (~large); load it on first View.
const DocumentViewerDrawer = defineAsyncComponent(
  () => import("./DocumentViewerDrawer.vue"),
);

const props = defineProps({
  companyId: { type: String, required: true },
  refreshKey: { type: Number, default: 0 },
});

const emit = defineEmits(["open-report", "files-changed"]);
const t = useT();

const payload = ref({
  groups: [],
  categories: [],
  source_classes: [],
  filters: { languages: [], statuses: [] },
  unresolved_intake_count: 0,
});
const loading = ref(true);
const error = ref("");
const savingId = ref("");

const categoryFilter = ref("all");
const sourceClassFilter = ref("all");
const languageFilter = ref("all");
const statusFilter = ref("all");
const query = ref("");

const backgroundFileInput = ref(null);
const backgroundUploading = ref(false);
const filtersOpen = ref(false);
const uploadError = ref("");
const launchingSummaryId = ref("");
const togglingId = ref("");

const errorMessage = computed(() =>
  error.value === "load" ? t("documents.load_error") : t("documents.action_error"),
);
const uploadErrorMessage = computed(() => t("documents.upload_error"));
const addFileBusy = computed(() => backgroundUploading.value);

function openAddFile() {
  backgroundFileInput.value?.click();
}

const previewing = ref(null);
const traceRow = ref(null);
const viewer = ref(null);

// In-browser viewer coverage (the slide-in drawer). PDFs/images/text keep
// the existing FilePreviewModal path.
const VIEWER_TYPES = new Set(["DOCX", "DOC", "MD"]);

function canViewInline(row) {
  if (row.backend === "generated_report") {
    return Object.keys(row.download_urls || {}).length > 0;
  }
  return VIEWER_TYPES.has(fileType(row));
}

function openViewer(row) {
  if (row.backend === "generated_report") {
    const order = { en: 0, zh: 1, internal: 2 };
    const sources = Object.keys(row.download_urls || {})
      .sort((a, b) => (order[a] ?? 9) - (order[b] ?? 9))
      .map((key) => ({
        key: String(key).toUpperCase(),
        url: downloadUrl(row, key),
        kind: "docx",
      }));
    if (!sources.length) return;
    viewer.value = { title: row.title || row.filename || "", sources };
    return;
  }
  const type = fileType(row);
  viewer.value = {
    title: row.title || row.filename || "",
    sources: [
      {
        key: type,
        url: downloadUrl(row),
        kind: type === "MD" ? "md" : "docx",
      },
    ],
  };
}

function closeViewer() {
  viewer.value = null;
}

const BACKGROUND_ACCEPT =
  ".pdf,.pptx,.docx,.doc,.txt,.md,.png,.jpg,.jpeg,.gif,.webp,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/*,text/*";

async function load() {
  loading.value = true;
  error.value = "";
  try {
    payload.value = await api.listCompanyDocuments(props.companyId);
  } catch {
    error.value = "load";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => props.companyId, load);
watch(() => props.refreshKey, load);

const categories = computed(() => payload.value.categories || []);
const sourceClasses = computed(() => payload.value.source_classes || []);
const languages = computed(() => payload.value.filters?.languages || []);
const statuses = computed(() => payload.value.filters?.statuses || []);

const filteredGroups = computed(() => {
  const q = query.value.trim().toLowerCase();
  const rows = (payload.value.groups || []).flatMap((group) => group.rows || []).filter((row) => {
    if (categoryFilter.value !== "all" && row.category !== categoryFilter.value) return false;
    if (sourceClassFilter.value !== "all" && row.source_class !== sourceClassFilter.value) return false;
    if (languageFilter.value !== "all" && (row.language || "unknown") !== languageFilter.value) return false;
    if (statusFilter.value !== "all" && (row.status || "pending") !== statusFilter.value) return false;
    if (!q) return true;
    return [row.title, row.filename, row.provenance?.origin, row.provenance?.url]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(q);
  });
  return [
    { id: "generated-memos", rows: rows.filter((row) => row.backend === "generated_report") },
    { id: "uploaded-documents", rows: rows.filter((row) => row.backend !== "generated_report") },
  ].filter((group) => group.rows.length);
});

const visibleCount = computed(() =>
  filteredGroups.value.reduce((total, group) => total + group.rows.length, 0),
);

const filtersActive = computed(
  () =>
    categoryFilter.value !== "all" ||
    sourceClassFilter.value !== "all" ||
    languageFilter.value !== "all" ||
    statusFilter.value !== "all" ||
    Boolean(query.value.trim()),
);

function clearDocumentFilters() {
  query.value = "";
  categoryFilter.value = "all";
  sourceClassFilter.value = "all";
  languageFilter.value = "all";
  statusFilter.value = "all";
}

function fmtDate(value) {
  return formatIsoDate(value, t("documents.pending_date"));
}

function fmtSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function rowSize(row) {
  return fmtSize(row.record?.size_bytes);
}

function sourceBadgeClass(sourceClass) {
  if (sourceClass === "generated memo") return "bg-accent-soft text-accent-ink border-accent/30";
  if (sourceClass === "unknown/pending") return "bg-notice-soft text-notice-ink border-notice/30";
  if (sourceClass === "internal note") return "bg-purple-soft text-purple-ink border-purple/30";
  if (String(sourceClass || "").includes("third-party") || String(sourceClass || "").includes("market")) {
    return "bg-teal-soft text-teal-ink border-teal/30";
  }
  if (String(sourceClass || "").includes("company")) {
    return "bg-purple-soft text-purple-ink border-purple/30";
  }
  return "bg-surface text-ink-secondary border-subtle";
}

function sourceBadgeLabel(row) {
  const value = String(row.source_class || "").toLowerCase();
  if (value === "generated memo") return t("documents.source_generated");
  if (value === "internal note") return t("documents.source_internal");
  if (value === "unknown/pending" || !value) return t("documents.source_pending");
  return row.source_class_label || row.source_class;
}

function fileType(row) {
  const source = String(row.filename || row.title || row.kind || "").toLowerCase();
  if (row.provenance?.url || row.kind === "url") return "URL";
  if (source.endsWith(".pdf") || row.kind === "pdf") return "PDF";
  if (/\.xlsx?$/.test(source) || ["xls", "xlsx"].includes(row.kind)) return "XLSX";
  if (source.endsWith(".md") || row.kind === "md") return "MD";
  if (/\.docx?$/.test(source) || ["doc", "docx"].includes(row.kind)) return "DOCX";
  if (/\.pptx?$/.test(source) || ["ppt", "pptx"].includes(row.kind)) return "PPTX";
  return String(row.type_badge || row.kind || "FILE").toUpperCase();
}

function fileTileClass(row) {
  const type = fileType(row);
  if (type === "PDF") return "bg-danger-soft text-danger-ink";
  if (type === "XLSX") return "bg-success-soft text-success-ink";
  if (type === "URL") return "bg-accent-soft text-accent-ink";
  if (type === "DOCX" || type === "DOC") return "bg-info-soft text-info-ink";
  if (type === "PPTX" || type === "PPT") return "bg-purple-soft text-purple-ink";
  if (type === "MD") return "bg-teal-soft text-teal-ink";
  return "bg-surface-muted text-ink-secondary";
}

function groupLabel(group) {
  const id = String(group.id || group.label || "").toLowerCase();
  if (id.includes("generated") || id.includes("memo") || id.includes("report")) {
    return t("documents.generated_memos");
  }
  return t("documents.uploaded_documents");
}

function openPreview(row) {
  // DOCX and Markdown render in the slide-in viewer; everything else keeps
  // the existing preview modal.
  if (VIEWER_TYPES.has(fileType(row))) {
    openViewer(row);
    return;
  }
  if (row.backend === "document_library") {
    previewing.value = {
      file: row.record,
      previewUrl: null,
      downloadUrl: null,
      previewableKinds: undefined,
    };
    return;
  }
  if (row.backend === "background_documents") {
    previewing.value = {
      file: row.record,
      previewUrl: api.researchFileUrl(props.companyId, row.record_id, { inline: true }),
      downloadUrl: api.researchFileUrl(props.companyId, row.record_id),
      previewableKinds: ["pdf", "image", "text"],
    };
  }
}

function closePreview() {
  previewing.value = null;
}

function downloadUrl(row, key = null) {
  if (row.backend === "document_library") return api.fileUrl(props.companyId, row.record_id);
  if (row.backend === "background_documents") return api.researchFileUrl(props.companyId, row.record_id);
  if (row.backend === "generated_report" && key && row.download_urls?.[key]) {
    return withApiToken(row.download_urls[key]);
  }
  return "#";
}

function canSummarize(row) {
  if (row.backend === "document_library") {
    return ["pdf", "ppt", "pptx"].includes(row.kind);
  }
  if (row.backend === "background_documents") return true;
  return false;
}

async function summarize(row) {
  if (row.backend === "document_library") {
    openSummary(props.companyId, row.record);
    return;
  }
  if (row.backend !== "background_documents") return;
  launchingSummaryId.value = row.id;
  try {
    await api.generateResearchFileSummary(props.companyId, row.record_id);
    await load();
  } catch {
    error.value = "action";
  } finally {
    launchingSummaryId.value = "";
  }
}

async function removeRow(row) {
  if (!window.confirm(`Delete ${row.title || row.filename}?`)) return;
  try {
    if (row.backend === "document_library") {
      await api.deleteFile(props.companyId, row.record_id);
    } else if (row.backend === "background_documents") {
      await api.deleteResearchFile(props.companyId, row.record_id);
    } else if (row.backend === "generated_report") {
      await api.deleteReport(row.record_id);
    }
    await load();
    emit("files-changed");
  } catch {
    error.value = "action";
  }
}

async function updateMetadata(row, patch) {
  savingId.value = row.id;
  try {
    await api.updateDocumentMetadata(props.companyId, row.backend, row.record_id, patch);
    await load();
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function setUseInReport(row, useInReport) {
  if (row.backend === "generated_report") return;
  if (Boolean(row.use_in_report) === Boolean(useInReport)) return;
  togglingId.value = row.id;
  error.value = "";
  try {
    await api.setDocumentUseInReport(
      props.companyId,
      row.backend,
      row.record_id,
      useInReport,
    );
    await load();
    emit("files-changed");
  } catch {
    error.value = "action";
  } finally {
    togglingId.value = "";
  }
}

async function uploadBackground(list) {
  if (!list?.length) return;
  backgroundUploading.value = true;
  uploadError.value = "";
  try {
    for (const file of list) {
      await api.uploadResearchFile(props.companyId, file);
    }
    await load();
    emit("files-changed");
  } catch {
    uploadError.value = "upload";
  } finally {
    backgroundUploading.value = false;
    if (backgroundFileInput.value) backgroundFileInput.value.value = "";
  }
}

function openReport(row) {
  if (row.report) emit("open-report", row.report);
}
</script>

<template>
  <section class="bg-surface border border-subtle rounded-card shadow-card p-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="vogue-label">{{ t("documents.eyebrow") }}</div>
        <h2 class="font-display text-xl font-semibold text-ink-primary">
          {{ t("documents.title") }}
        </h2>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="btn-bordered focus-ring"
          :disabled="addFileBusy"
          :aria-label="t('documents.add_file')"
          @click="openAddFile"
        >
          <Loader2 v-if="addFileBusy" class="h-4 w-4 animate-spin" />
          <UploadCloud v-else class="h-4 w-4" />
          {{ t("documents.add_file") }}
        </button>
        <button
          type="button"
          class="btn-bordered focus-ring"
          :aria-expanded="filtersOpen"
          :aria-pressed="filtersOpen || filtersActive"
          @click="filtersOpen = !filtersOpen"
        >
          <Filter class="h-4 w-4" />
          {{ t("documents.filter_toggle") }}
          <span
            v-if="filtersActive"
            class="mono-data rounded-pill bg-accent-soft px-1.5 text-caption1 text-accent-ink"
          >
            {{ visibleCount }}
          </span>
        </button>
      </div>
      <input
        ref="backgroundFileInput"
        type="file"
        multiple
        :accept="BACKGROUND_ACCEPT"
        class="hidden"
        @change="uploadBackground(Array.from($event.target.files || []))"
      />
    </div>

    <div v-if="uploadError" class="mt-3 banner-danger">
      {{ uploadErrorMessage }}
    </div>

    <div
      v-if="filtersOpen || filtersActive"
      class="mt-5 space-y-3 rounded-subbox border border-subtle bg-surface-muted/60 p-3"
    >
      <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
        <span>
          <span class="font-mono text-ink-primary">{{ visibleCount }}</span>
          {{ t("documents.visible") }}
          <span v-if="payload.unresolved_intake_count">
            · <span class="font-mono text-notice-ink">{{ payload.unresolved_intake_count }}</span>
            {{ t("documents.unresolved") }}
          </span>
        </span>
      </div>
      <div class="grid min-w-0 gap-3 lg:grid-cols-[minmax(12rem,1.4fr)_repeat(4,minmax(0,1fr))]">
        <label class="relative block min-w-0">
          <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
          <input
            v-model="query"
            type="search"
            :placeholder="t('documents.filter_placeholder')"
            class="field !pl-9 pr-3 focus-ring"
          />
        </label>
        <select
          v-model="categoryFilter"
          class="field min-w-0 truncate text-ink-secondary"
          :title="t('documents.all_categories')"
        >
          <option value="all">{{ t("documents.all_categories") }}</option>
          <option v-for="category in categories" :key="category.id" :value="category.id">
            {{ category.label }}
          </option>
        </select>
        <select
          v-model="sourceClassFilter"
          class="field min-w-0 truncate text-ink-secondary"
          :title="t('documents.all_source_classes')"
        >
          <option value="all">{{ t("documents.all_source_classes") }}</option>
          <option v-for="sourceClass in sourceClasses" :key="sourceClass" :value="sourceClass">
            {{ sourceClass }}
          </option>
        </select>
        <select
          v-model="languageFilter"
          class="field min-w-0 truncate text-ink-secondary"
          :title="t('documents.all_languages')"
        >
          <option value="all">{{ t("documents.all_languages") }}</option>
          <option v-for="language in languages" :key="language" :value="language">
            {{ language.toUpperCase() }}
          </option>
        </select>
        <select
          v-model="statusFilter"
          class="field min-w-0 truncate text-ink-secondary"
          :title="t('documents.all_statuses')"
        >
          <option value="all">{{ t("documents.all_statuses") }}</option>
          <option v-for="status in statuses" :key="status" :value="status">
            {{ humanizeStatus(status, t("memo.pending"), appLanguage) }}
          </option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="mt-6 flex items-center gap-2 text-sm text-ink-muted">
      <Loader2 class="h-4 w-4 animate-spin" />
      {{ t("documents.loading") }}
    </div>
    <div v-else-if="error" class="mt-6 flex items-start gap-2 banner-danger">
      <AlertCircle class="mt-0.5 h-4 w-4" />
      {{ errorMessage }}
    </div>
    <div v-else-if="visibleCount === 0" class="mt-6 rounded-subbox border border-dashed border-subtle bg-surface-muted p-6 text-sm text-ink-muted">
      <p>{{ t("documents.empty") }}</p>
      <button
        v-if="payload.unresolved_intake_count && filtersActive"
        type="button"
        class="btn-tinted mt-3 text-xs focus-ring"
        @click="clearDocumentFilters"
      >
        {{ t("documents.show_awaiting", { count: payload.unresolved_intake_count }) }}
      </button>
    </div>

    <div v-else class="mt-6 space-y-5">
      <section
        v-for="group in filteredGroups"
        :key="group.id"
        class="overflow-hidden rounded-subbox border border-subtle bg-surface"
      >
        <div class="flex items-center justify-between gap-3 border-b border-subtle px-4 py-3">
          <div class="flex items-center gap-2">
            <ChevronDown class="h-4 w-4 text-ink-muted" />
            <h3 class="font-display text-base font-semibold text-ink-primary">{{ groupLabel(group) }}</h3>
          </div>
          <span class="font-mono text-xs text-ink-muted">{{ group.rows.length }}</span>
        </div>
        <ul class="divide-y divide-subtle">
          <li
            v-for="row in group.rows"
            :key="row.id"
            class="px-4 py-4"
          >
            <div class="flex flex-col gap-3 lg:flex-row lg:items-start">
              <div
                class="mono-data grid h-11 w-11 shrink-0 place-items-center rounded-row text-[10px] font-bold"
                :class="fileTileClass(row)"
                aria-hidden="true"
              >
                {{ fileType(row) }}
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <button
                    v-if="row.backend === 'generated_report'"
                    type="button"
                    @click="openReport(row)"
                    class="truncate text-left text-sm font-semibold text-ink-primary hover:text-accent-ink focus-ring rounded"
                  >
                    {{ row.title }}
                  </button>
                  <span v-else class="truncate text-sm font-semibold text-ink-primary">
                    {{ row.title }}
                  </span>
                  <span class="rounded-full border px-2 py-0.5 text-[11px]" :class="sourceBadgeClass(row.source_class)">
                    {{ sourceBadgeLabel(row) }}
                  </span>
                  <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] text-ink-muted">
                    {{ humanizeStatus(row.status, t("memo.pending"), appLanguage) }}
                  </span>
                </div>
                <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
                  <span>{{ row.filename || t("documents.no_file") }}</span>
                  <span v-if="rowSize(row)">{{ rowSize(row) }}</span>
                  <span class="mono-data">{{ fmtDate(row.captured_at || row.uploaded_at) }}</span>
                  <span>{{ (row.language || "unknown").toUpperCase() }}</span>
                  <span v-if="row.provenance?.origin">{{ t("documents.source") }}: {{ row.provenance.origin }}</span>
                  <span v-if="row.source_trace_count">{{ row.source_trace_count }} {{ t("documents.traces") }}</span>
                </div>
                <label
                  v-if="row.backend !== 'generated_report'"
                  class="mt-2 inline-flex items-center gap-2 text-xs font-medium text-ink-secondary"
                  :title="row.use_in_report_locked ? t('documents.use_in_report_locked') : t('documents.use_in_report_help')"
                >
                  <input
                    type="checkbox"
                    class="memo-checkbox focus-ring"
                    :checked="row.use_in_report ?? row.backend === 'background_documents'"
                    :disabled="togglingId === row.id || row.use_in_report_locked"
                    :aria-label="t('documents.use_in_report')"
                    @change="setUseInReport(row, $event.target.checked)"
                  />
                  {{ t("documents.use_in_report") }}
                  <Loader2 v-if="togglingId === row.id" class="h-3 w-3 animate-spin text-ink-muted" />
                </label>
                <p
                  v-if="row.summary?.exec_summary?.en || row.quick_summary?.summary_en || row.quick_summary?.summary"
                  class="mt-2 line-clamp-2 text-xs leading-relaxed text-ink-secondary"
                >
                  {{ row.summary?.exec_summary?.en || row.quick_summary?.summary_en || row.quick_summary?.summary }}
                </p>
                <div v-if="row.editable_metadata" class="mt-3 flex flex-wrap items-center gap-2 text-xs">
                  <select
                    :value="row.category"
                    :disabled="savingId === row.id"
                    class="rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                    @change="updateMetadata(row, { category: $event.target.value })"
                  >
                    <option v-for="category in categories" :key="category.id" :value="category.id">
                      {{ category.label }}
                    </option>
                  </select>
                  <select
                    :value="row.source_class"
                    :disabled="savingId === row.id"
                    class="rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                    @change="updateMetadata(row, { source_class: $event.target.value })"
                  >
                    <option v-for="sourceClass in sourceClasses" :key="sourceClass" :value="sourceClass">
                      {{ sourceClass }}
                    </option>
                  </select>
                  <span v-if="savingId === row.id" class="inline-flex items-center gap-1 text-ink-muted">
                    <Loader2 class="h-3 w-3 animate-spin" />
                    {{ t("common.saving") }}
                  </span>
                </div>
              </div>

              <div class="flex shrink-0 flex-wrap items-center gap-1.5">
                <button
                  v-if="row.backend === 'generated_report' && canViewInline(row)"
                  type="button"
                  @click="openViewer(row)"
                  class="btn-filled rounded-full px-3 py-1.5 text-xs font-semibold hover:bg-accent-hover focus-ring"
                >
                  <Eye class="h-3.5 w-3.5" />
                  {{ t("documents.view") }}
                </button>
                <button
                  v-if="row.backend === 'generated_report'"
                  type="button"
                  @click="openReport(row)"
                  class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
                >
                  {{ t("documents.open") }}
                </button>
                <button
                  type="button"
                  @click="traceRow = row"
                  class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
                >
                  <FileText class="h-3.5 w-3.5" />
                  {{ t("documents.source_trace") }}
                </button>
                <button
                  v-if="canSummarize(row)"
                  type="button"
                  @click="summarize(row)"
                  :disabled="launchingSummaryId === row.id"
                  class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted disabled:opacity-60 focus-ring"
                >
                  <Loader2 v-if="launchingSummaryId === row.id" class="h-3.5 w-3.5 animate-spin" />
                  <AiMark v-else class="h-3.5 w-3.5" />
                  {{ t("documents.summarize") }}
                </button>
                <button
                  v-if="row.backend !== 'generated_report'"
                  type="button"
                  @click="openPreview(row)"
                  class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
                >
                  <Eye class="h-3.5 w-3.5" />
                  {{ t("documents.view") }}
                </button>
                <template v-if="row.backend === 'generated_report'">
                  <a
                    v-for="(url, key) in row.download_urls || {}"
                    :key="key"
                    :href="downloadUrl(row, key)"
                    class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs uppercase text-ink-secondary hover:bg-surface-muted focus-ring"
                  >
                    <Download class="h-3.5 w-3.5" />
                    {{ String(key).toUpperCase() }}
                  </a>
                </template>
                <a
                  v-else
                  :href="downloadUrl(row)"
                  class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
                >
                  <Download class="h-3.5 w-3.5" />
                  {{ t("documents.export") }}
                </a>
                <button
                  v-if="row.editable_metadata || (row.backend === 'generated_report' && isTerminalReportStatus(row.status))"
                  type="button"
                  @click="removeRow(row)"
                  class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-muted hover:border-danger/40 hover:bg-danger/10 hover:text-danger focus-ring"
                >
                  <Trash2 class="h-3.5 w-3.5" />
                  {{ t("common.delete") }}
                </button>
              </div>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <div
      v-if="traceRow"
      class="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-subtle bg-surface p-5 shadow-card-raised"
    >
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="vogue-label">{{ t("documents.source_trace") }}</div>
          <h3 class="mt-1 font-display text-title3 text-ink-primary">
            {{ traceRow.title }}
          </h3>
        </div>
        <button
          type="button"
          @click="traceRow = null"
          class="rounded-full border border-subtle px-3 py-1 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
        >
          {{ t("documents.close") }}
        </button>
      </div>
      <dl class="mt-5 space-y-3 text-sm">
        <div>
          <dt class="text-footnote font-semibold text-ink-muted">{{ t("documents.source_class") }}</dt>
          <dd class="mt-1 text-ink-primary">{{ traceRow.source_class }}</dd>
        </div>
        <div>
          <dt class="text-footnote font-semibold text-ink-muted">{{ t("documents.origin") }}</dt>
          <dd class="mt-1 text-ink-primary">{{ traceRow.provenance?.origin || t("memo.pending") }}</dd>
        </div>
        <div>
          <dt class="text-footnote font-semibold text-ink-muted">{{ t("documents.captured") }}</dt>
          <dd class="mono-data mt-1 text-ink-primary">{{ formatIsoDate(traceRow.provenance?.captured_at, t("memo.pending")) }}</dd>
        </div>
        <div v-if="traceRow.provenance?.url">
          <dt class="text-footnote font-semibold text-ink-muted">{{ t("documents.url") }}</dt>
          <dd class="mt-1 break-all text-ink-primary">{{ traceRow.provenance.url }}</dd>
        </div>
      </dl>
      <div class="mt-5">
        <h4 class="text-sm font-semibold text-ink-primary">{{ t("documents.source_refs") }}</h4>
        <ul class="mt-2 space-y-2 text-xs text-ink-secondary">
          <li
            v-for="sourceRef in traceRow.source_refs || []"
            :key="`${sourceRef.title}-${sourceRef.file}-${sourceRef.url}`"
            class="rounded-subbox border border-subtle bg-surface-muted p-3"
          >
            <div class="font-semibold text-ink-primary">{{ sourceRef.title || t("research.source_pending") }}</div>
            <div class="mt-1">{{ sourceRef.source_class || traceRow.source_class }}</div>
          </li>
        </ul>
      </div>
      <div class="mt-5">
        <h4 class="text-sm font-semibold text-ink-primary">{{ t("documents.trace_excerpts") }}</h4>
        <div v-if="!(traceRow.source_traces || []).length" class="mt-2 text-sm text-ink-muted">
          {{ t("documents.no_excerpts") }}
        </div>
        <ul v-else class="mt-2 space-y-2 text-xs text-ink-secondary">
          <li
            v-for="(trace, index) in traceRow.source_traces"
            :key="`${trace.locator}-${index}`"
            class="rounded-subbox border border-subtle bg-surface-muted p-3"
          >
            <div class="font-semibold text-ink-primary">{{ trace.locator || trace.label || "Document" }}</div>
            <p class="mt-1 leading-relaxed">{{ trace.excerpt || trace.text }}</p>
            <div v-if="trace.confidence" class="mt-2 text-[11px] text-footnote font-semibold text-ink-muted">
              {{ t("documents.confidence", { value: trace.confidence }) }}
            </div>
          </li>
        </ul>
      </div>
    </div>

    <FilePreviewModal
      :company-id="companyId"
      :file="previewing?.file || null"
      :preview-url="previewing?.previewUrl || null"
      :download-url="previewing?.downloadUrl || null"
      :previewable-kinds="previewing?.previewableKinds"
      @close="closePreview"
    />

    <DocumentViewerDrawer
      v-if="viewer"
      :title="viewer.title"
      :sources="viewer.sources"
      @close="closeViewer"
    />
  </section>
</template>
