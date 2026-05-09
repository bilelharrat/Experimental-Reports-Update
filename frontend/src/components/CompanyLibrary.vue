<script setup>
import { computed, onMounted, ref, watch } from "vue";
import {
  FileText,
  FileImage,
  Presentation,
  Loader2,
  Trash2,
  UploadCloud,
  Sparkles,
  Download,
  Eye,
  ChevronRight,
} from "lucide-vue-next";
import { api } from "../api.js";
import FilePreviewModal from "./FilePreviewModal.vue";
import { openSummary } from "../state.js";

const props = defineProps({
  companyId: { type: String, required: true },
  refreshKey: { type: Number, default: 0 },
});
const emit = defineEmits(["open-report", "files-changed"]);

const previewing = ref(null); // file object | null

function summarize(f) {
  openSummary(props.companyId, f);
}

const files = ref([]);
const reports = ref([]);
const loading = ref(true);
const error = ref(null);
const uploading = ref(false);
const uploadError = ref(null);
const dragOver = ref(false);
const fileInput = ref(null);
const uploadLanguage = ref("en");
const languageFilter = ref("all"); // "all" | "en" | "zh"

const LANG_LABELS = { en: "English", zh: "中文" };

const ACCEPT = ".pdf,.ppt,.pptx,application/pdf,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation";

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [f, r] = await Promise.all([
      api.listFiles(props.companyId),
      api.listCompanyReports(props.companyId),
    ]);
    files.value = f;
    reports.value = r;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => props.companyId, load);
watch(() => props.refreshKey, load);

async function uploadFiles(list) {
  if (!list || list.length === 0) return;
  uploading.value = true;
  uploadError.value = null;
  try {
    for (const f of list) {
      await api.uploadFile(props.companyId, f, null, uploadLanguage.value);
    }
    await load();
    emit("files-changed");
  } catch (e) {
    uploadError.value = e.message;
  } finally {
    uploading.value = false;
    if (fileInput.value) fileInput.value.value = "";
  }
}

function onPick(e) {
  uploadFiles(Array.from(e.target.files || []));
}
function onDrop(e) {
  e.preventDefault();
  dragOver.value = false;
  uploadFiles(Array.from(e.dataTransfer.files || []));
}

async function removeFile(f) {
  if (!confirm(`Remove ${f.filename}?`)) return;
  try {
    await api.deleteFile(props.companyId, f.id);
    await load();
    emit("files-changed");
  } catch (e) {
    uploadError.value = e.message;
  }
}

function fmtSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function iconFor(kind) {
  if (kind === "pdf") return FileText;
  if (kind === "ppt" || kind === "pptx") return Presentation;
  return FileImage;
}

function summaryPreview(summary) {
  if (!summary) return "";
  // Prefer source language; fall back to either side.
  const lang = summary.language === "zh" ? "zh" : "en";
  const text =
    summary.exec_summary?.[lang] ||
    summary.exec_summary?.en ||
    summary.exec_summary?.zh ||
    "";
  if (!text) return "";
  // Pull the first 1-2 sentences, ~220 chars max.
  const trimmed = text.trim();
  const m = trimmed.match(/^(.+?[.!?。!?])\s*(.+?[.!?。!?])?/);
  const candidate = m ? (m[2] ? `${m[1]} ${m[2]}` : m[1]) : trimmed;
  return candidate.length > 240
    ? candidate.slice(0, 235).trimEnd() + "…"
    : candidate;
}

function langMatches(asset) {
  if (languageFilter.value === "all") return true;
  return (asset.language || "en") === languageFilter.value;
}

const sortedReports = computed(() =>
  [...reports.value]
    .filter(langMatches)
    .sort((a, b) =>
      String(b.created_at).localeCompare(String(a.created_at)),
    ),
);

const filteredFiles = computed(() => files.value.filter(langMatches));

const counts = computed(() => {
  const tally = (arr, code) => arr.filter((x) => (x.language || "en") === code).length;
  return {
    en: tally(reports.value, "en") + tally(files.value, "en"),
    zh: tally(reports.value, "zh") + tally(files.value, "zh"),
  };
});
</script>

<template>
  <section class="bg-surface border border-subtle rounded-card shadow-card p-6">
    <div class="flex items-center justify-between mb-1">
      <h2 class="font-display text-lg font-semibold text-ink-primary">Library</h2>
      <span class="text-xs text-ink-muted">
        {{ reports.length }} reports · {{ files.length }} files
      </span>
    </div>
    <p class="text-sm text-ink-muted mb-4">
      Generated reports and uploaded presentations or PDFs for this company.
      Each asset has an English and Chinese version.
    </p>

    <!-- Language filter -->
    <div class="flex items-center gap-1 mb-4">
      <button
        v-for="opt in [
          { code: 'all', label: 'All' },
          { code: 'en', label: 'English' },
          { code: 'zh', label: '中文' },
        ]"
        :key="opt.code"
        type="button"
        @click="languageFilter = opt.code"
        :class="[
          'text-xs px-2.5 py-1 rounded-md border focus-ring transition',
          languageFilter === opt.code
            ? 'bg-accent text-white border-accent'
            : 'bg-surface-muted border-subtle text-ink-secondary hover:border-strong',
        ]"
      >
        {{ opt.label
        }}<span
          v-if="opt.code !== 'all'"
          class="ml-1 opacity-70"
          >· {{ counts[opt.code] }}</span
        >
      </button>
    </div>

    <!-- Upload zone -->
    <div
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop="onDrop"
      :class="[
        'rounded-lg border-2 border-dashed px-4 py-5 text-center transition mb-5',
        dragOver
          ? 'border-accent bg-accent-soft/40'
          : 'border-subtle bg-surface-muted hover:border-strong',
      ]"
    >
      <UploadCloud class="h-6 w-6 text-ink-muted mx-auto mb-1" />
      <div class="text-sm text-ink-secondary">
        Drop a PDF or PowerPoint here, or
        <button
          type="button"
          @click="fileInput?.click()"
          class="text-accent hover:text-accent-hover underline focus-ring rounded"
        >
          browse
        </button>
      </div>
      <div class="text-xs text-ink-muted mt-0.5">PDF, PPT, PPTX · up to 100MB</div>
      <div class="mt-3 inline-flex items-center gap-1 text-xs text-ink-muted">
        <span>Language:</span>
        <button
          v-for="opt in [
            { code: 'en', label: 'English' },
            { code: 'zh', label: '中文' },
          ]"
          :key="opt.code"
          type="button"
          @click="uploadLanguage = opt.code"
          :class="[
            'px-2 py-0.5 rounded border focus-ring',
            uploadLanguage === opt.code
              ? 'bg-accent-soft text-accent-ink border-accent/40'
              : 'bg-surface border-subtle text-ink-secondary hover:border-strong',
          ]"
        >
          {{ opt.label }}
        </button>
      </div>
      <input
        ref="fileInput"
        type="file"
        :accept="ACCEPT"
        multiple
        class="hidden"
        @change="onPick"
      />
      <div
        v-if="uploading"
        class="mt-2 text-xs text-ink-muted inline-flex items-center gap-1.5"
      >
        <Loader2 class="h-3 w-3 animate-spin" /> Uploading…
      </div>
      <div v-if="uploadError" class="mt-2 text-xs text-danger">{{ uploadError }}</div>
    </div>

    <div v-if="error" class="text-sm text-danger mb-3">{{ error }}</div>

    <!-- Tabs -->
    <div v-if="loading" class="text-sm text-ink-muted flex items-center gap-2">
      <Loader2 class="h-4 w-4 animate-spin" /> Loading…
    </div>

    <div v-else-if="reports.length === 0 && files.length === 0" class="text-sm text-ink-muted">
      No reports or uploads yet.
    </div>

    <div
      v-else-if="sortedReports.length === 0 && filteredFiles.length === 0"
      class="text-sm text-ink-muted"
    >
      Nothing in {{ LANG_LABELS[languageFilter] || languageFilter }} yet.
    </div>

    <div v-else class="space-y-5">
      <!-- Generated reports -->
      <div v-if="sortedReports.length > 0">
        <div class="text-xs font-semibold uppercase tracking-wide text-ink-muted mb-2">
          Generated reports
        </div>
        <ul class="space-y-1.5">
          <li
            v-for="r in sortedReports"
            :key="r.id"
            class="flex items-center gap-3 px-3 py-2 rounded-lg border border-subtle bg-surface-muted hover:bg-surface focus-within:bg-surface"
          >
            <Sparkles class="h-4 w-4 text-accent shrink-0" />
            <button
              type="button"
              @click="emit('open-report', r)"
              class="flex-1 min-w-0 text-left focus-ring rounded"
            >
              <div class="text-sm font-medium text-ink-primary truncate">
                {{ r.report_type }}
                <span class="text-ink-muted">· {{ r.audience }}</span>
              </div>
              <div class="text-xs text-ink-muted truncate">
                {{ fmtDate(r.created_at) }}
                · v.{{ r.id.slice(0, 6) }}
              </div>
            </button>
            <span
              class="text-xs px-1.5 py-0.5 rounded bg-surface border border-subtle text-ink-secondary font-mono"
              :title="LANG_LABELS[r.language || 'en']"
              >{{ (r.language || "en").toUpperCase() }}</span
            >
            <span
              v-if="r.status === 'complete'"
              class="text-xs px-1.5 py-0.5 rounded bg-success-soft text-success-ink"
              >Complete</span
            >
            <span
              v-else
              class="text-xs px-1.5 py-0.5 rounded bg-warning-soft text-warning-ink"
              >{{ r.progress }}%</span
            >
          </li>
        </ul>
      </div>

      <!-- Uploaded files -->
      <div v-if="filteredFiles.length > 0">
        <div class="text-xs font-semibold uppercase tracking-wide text-ink-muted mb-2">
          Uploads
        </div>
        <ul class="space-y-1.5">
          <li
            v-for="f in filteredFiles"
            :key="f.id"
            class="rounded-lg border border-subtle bg-surface-muted"
          >
            <div class="flex items-center gap-3 px-3 py-2">
              <component
                :is="iconFor(f.kind)"
                class="h-4 w-4 text-ink-muted shrink-0"
              />
              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium text-ink-primary truncate">
                  {{ f.label || f.filename }}
                </div>
                <div class="text-xs text-ink-muted truncate">
                  <span class="uppercase">{{ f.kind }}</span>
                  · {{ fmtSize(f.size_bytes) }}
                  · {{ fmtDate(f.uploaded_at) }}
                  <span v-if="f.summary" class="text-accent ml-1">· summary ready</span>
                </div>
              </div>
            <span
              class="text-xs px-1.5 py-0.5 rounded bg-surface border border-subtle text-ink-secondary font-mono"
              :title="LANG_LABELS[f.language || 'en']"
              >{{ (f.language || "en").toUpperCase() }}</span
            >
            <button
              type="button"
              @click="summarize(f)"
              class="p-1.5 rounded hover:bg-accent-soft text-ink-muted hover:text-accent-ink focus-ring"
              :title="
                f.summary
                  ? 'Open bilingual summary (cached)'
                  : 'Generate bilingual summary'
              "
            >
              <Sparkles
                class="h-4 w-4"
                :class="f.summary ? 'text-accent' : ''"
              />
            </button>
            <button
              type="button"
              @click="previewing = f"
              class="p-1.5 rounded hover:bg-surface text-ink-muted hover:text-ink-primary focus-ring"
              :title="`Preview ${f.filename}`"
            >
              <Eye class="h-4 w-4" />
            </button>
            <a
              :href="api.fileUrl(companyId, f.id)"
              :download="f.filename"
              class="p-1.5 rounded hover:bg-surface text-ink-muted hover:text-ink-primary focus-ring"
              :title="`Download ${f.filename}`"
            >
              <Download class="h-4 w-4" />
            </a>
            <button
              type="button"
              @click="removeFile(f)"
              class="p-1.5 rounded hover:bg-danger-soft text-ink-muted hover:text-danger-ink focus-ring"
              :title="`Remove ${f.filename}`"
            >
              <Trash2 class="h-4 w-4" />
            </button>
            </div>
            <button
              v-if="f.summary && f.summary.exec_summary"
              type="button"
              @click="summarize(f)"
              class="w-full text-left px-3 py-2 border-t border-subtle hover:bg-surface focus-ring rounded-b-lg flex items-start gap-2 group"
              :title="`Open full bilingual summary for ${f.filename}`"
            >
              <Sparkles class="h-3.5 w-3.5 text-accent shrink-0 mt-0.5" />
              <p class="flex-1 text-sm text-ink-secondary leading-snug line-clamp-2">
                {{ summaryPreview(f.summary) }}
              </p>
              <ChevronRight
                class="h-3.5 w-3.5 text-ink-muted shrink-0 mt-0.5 group-hover:text-ink-primary"
              />
            </button>
          </li>
        </ul>
      </div>
    </div>

    <FilePreviewModal
      :company-id="companyId"
      :file="previewing"
      @close="previewing = null"
    />
    <!-- DeckSummaryModal is mounted globally in App.vue and driven by
         the shared activeSummaryTarget state — see state.js. -->
  </section>
</template>
