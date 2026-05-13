<script setup>
// Research-library upload section. This is Serena's per-company
// "Background Documents" folder — files dropped here are intended as
// inputs for the investment memo (separate from the Document Library
// which is the user's general per-company file storage).
//
// See docs/architecture.md for the two-feature split.

import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Eye,
  FileImage,
  FileText,
  Image,
  Loader2,
  Sparkles,
  Trash2,
  UploadCloud,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import FilePreviewModal from "./FilePreviewModal.vue";

const t = useT();

const props = defineProps({
  companyId: { type: String, required: true },
});

const files = ref([]);
const loading = ref(true);
const error = ref(null);
const uploading = ref(false);
const uploadError = ref(null);
const dragOver = ref(false);
const fileInput = ref(null);
// Locally-tracked in-flight summary jobs (the backend is the source of
// truth via the active-jobs rail; this is the optimistic state until
// the JSONL job_init lands and the poll picks it up).
const launching = ref(new Set());
const summaryError = ref({});  // file_id -> error message
// Currently-previewed research file (null = modal closed).
const previewing = ref(null);
const previewUrl = computed(() =>
  previewing.value
    ? api.researchFileUrl(props.companyId, previewing.value.id, { inline: true })
    : null,
);
const downloadUrl = computed(() =>
  previewing.value
    ? api.researchFileUrl(props.companyId, previewing.value.id)
    : null,
);
// Per-file language toggle for the bilingual summary fields ("en" | "zh").
// Used for both the image description block AND the non-image
// title/summary/key_points/key_figures bilingual fields.
const summaryLang = ref({});    // file_id -> "en" | "zh"

// Per-file expand state. Each file's full summary details (summary,
// key_points, key_figures, entities, topics) live behind this toggle so
// the list stays scannable; click the row to expand one.
const expandedFiles = ref(new Set());
function isExpanded(fileId) {
  return expandedFiles.value.has(fileId);
}
function toggleExpanded(fileId) {
  const next = new Set(expandedFiles.value);
  if (next.has(fileId)) next.delete(fileId);
  else next.add(fileId);
  expandedFiles.value = next;
}

function summaryLangFor(f) {
  return summaryLang.value[f.id] || "en";
}
function toggleSummaryLang(fileId, lang) {
  summaryLang.value = { ...summaryLang.value, [fileId]: lang };
}

function isImage(f) {
  return f && f.kind === "image";
}

// Pick the EN or ZH variant of a bilingual field; fall back to a legacy
// single-field shape (e.g. older quick_summary records that only have
// `summary`, not `summary_en`/`summary_zh`).
function bilingual(qs, baseField, lang) {
  if (!qs) return null;
  const enKey = `${baseField}_en`;
  const zhKey = `${baseField}_zh`;
  if (lang === "zh") {
    if (qs[zhKey] != null && qs[zhKey] !== "") return qs[zhKey];
    if (qs[enKey] != null && qs[enKey] !== "") return qs[enKey];
  } else {
    if (qs[enKey] != null && qs[enKey] !== "") return qs[enKey];
    if (qs[zhKey] != null && qs[zhKey] !== "") return qs[zhKey];
  }
  // Legacy single-field shape.
  return qs[baseField] || null;
}

function titleFor(f) {
  return bilingual(f.quick_summary, "title", summaryLangFor(f));
}
function summaryFor(f) {
  return bilingual(f.quick_summary, "summary", summaryLangFor(f));
}
function keyPointsFor(f) {
  const qs = f && f.quick_summary;
  if (!qs) return [];
  const lang = summaryLangFor(f);
  const en = Array.isArray(qs.key_points_en) ? qs.key_points_en : null;
  const zh = Array.isArray(qs.key_points_zh) ? qs.key_points_zh : null;
  if (lang === "zh" && zh && zh.length) return zh;
  if (lang === "en" && en && en.length) return en;
  if (en && en.length) return en;
  if (zh && zh.length) return zh;
  return Array.isArray(qs.key_points) ? qs.key_points : [];
}
function figureLabel(fig, lang) {
  if (!fig) return "";
  if (lang === "zh") return fig.label_zh || fig.label_en || fig.label || "";
  return fig.label_en || fig.label_zh || fig.label || "";
}
function figureContext(fig, lang) {
  if (!fig) return "";
  if (lang === "zh") return fig.context_zh || fig.context_en || fig.context || "";
  return fig.context_en || fig.context_zh || fig.context || "";
}
function descriptionFor(f) {
  const qs = f && f.quick_summary;
  if (!qs) return null;
  const lang = summaryLangFor(f);
  const text = lang === "zh" ? qs.description_zh : qs.description_en;
  return text || null;
}

// One-liner preview for the collapsed row. Prefers the bilingual summary
// (in whichever language the user has the toggle set to) and falls back to
// the legacy single-field shape. Trimmed to the first sentence-ish, with
// a hard length cap so long ones don't push the row out of shape.
function oneLinerFor(f) {
  const text = summaryFor(f);
  if (!text) return null;
  const trimmed = String(text).trim();
  // Cut at the first sentence terminator (latin or CJK), if it appears
  // early enough; otherwise hard-truncate.
  const m = trimmed.match(/^([^.!?。！？]{20,180}[.!?。！？])/);
  const candidate = m ? m[1] : trimmed;
  return candidate.length > 180 ? candidate.slice(0, 175).trimEnd() + "…" : candidate;
}

// Badge label for the document's detected source language.
function sourceLangLabel(qs) {
  const code = qs && qs.language;
  if (code === "en") return "EN";
  if (code === "zh") return "中文";
  if (code) return String(code).toUpperCase();
  return null;
}

// Does this file have any bilingual content worth showing a toggle for?
function hasBilingualSummary(qs) {
  if (!qs) return false;
  return Boolean(
    qs.summary_en ||
    qs.summary_zh ||
    qs.title_en ||
    qs.title_zh ||
    (Array.isArray(qs.key_points_en) && qs.key_points_en.length) ||
    (Array.isArray(qs.key_points_zh) && qs.key_points_zh.length) ||
    qs.description_en ||
    qs.description_zh,
  );
}

// File-type filter for the dropzone hint and (loose) <input accept>.
const ACCEPT =
  ".pdf,.pptx,.docx,.doc,.txt,.md,.png,.jpg,.jpeg,.gif,.webp," +
  "application/pdf," +
  "application/vnd.openxmlformats-officedocument.presentationml.presentation," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "image/*,text/*";

let pollTimer = null;

async function load() {
  try {
    const fresh = await api.listResearchFiles(props.companyId);
    files.value = fresh;
    error.value = null;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

// Active-jobs poll. Rail-polled by ActiveJobsRail every 3s already, but
// the file list needs its own poll because the *summary content* lives
// on the file record, not on the rail entry. We poll at 2s while any
// summary is in-flight (locally launched or visible on the rail).
async function syncWithRail() {
  let activeFileIds = new Set([...launching.value]);
  try {
    const jobs = await api.listActiveJobs();
    for (const j of jobs) {
      if (j.kind === "research_summary"
          && j.company_id === props.companyId
          && j.file_id) {
        activeFileIds.add(j.file_id);
      }
    }
  } catch {
    // network blip — fall through
  }
  // Refresh the file list whenever something might have changed.
  await load();
  // Drop launching entries whose summary has landed (or whose job exited).
  const newLaunching = new Set();
  for (const id of launching.value) {
    const f = files.value.find((x) => x.id === id);
    if (f && f.quick_summary && !f.quick_summary.error) continue;
    if (activeFileIds.has(id)) newLaunching.add(id);
  }
  launching.value = newLaunching;
}

const anyInFlight = computed(() =>
  launching.value.size > 0 ||
  files.value.some((f) =>
    f.quick_summary && f.quick_summary.in_flight,
  ),
);

function startPolling() {
  stopPolling();
  pollTimer = setInterval(syncWithRail, 2000);
}
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted(async () => {
  loading.value = true;
  await load();
  startPolling();
});
watch(() => props.companyId, async () => {
  loading.value = true;
  launching.value = new Set();
  await load();
});
onBeforeUnmount(stopPolling);

async function uploadFiles(list) {
  if (!list || list.length === 0) return;
  uploading.value = true;
  uploadError.value = null;
  try {
    for (const f of list) {
      await api.uploadResearchFile(props.companyId, f);
    }
    await load();
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
  uploadFiles(Array.from(e.dataTransfer?.files || []));
}
function onDragOver(e) {
  e.preventDefault();
  dragOver.value = true;
}
function onDragLeave() {
  dragOver.value = false;
}

async function summarize(f) {
  if (launching.value.has(f.id)) return;
  launching.value = new Set([...launching.value, f.id]);
  delete summaryError.value[f.id];
  summaryError.value = { ...summaryError.value };
  // Optimistically mark the row as "summary cleared, running" so the UI
  // shows the loader without waiting for the next poll.
  const idx = files.value.findIndex((x) => x.id === f.id);
  if (idx >= 0) {
    files.value[idx] = { ...files.value[idx], quick_summary: null };
  }
  try {
    // Async kickoff: backend returns 202 + job descriptor immediately.
    await api.generateResearchFileSummary(props.companyId, f.id);
  } catch (e) {
    summaryError.value = { ...summaryError.value, [f.id]: e.message };
    const next = new Set(launching.value);
    next.delete(f.id);
    launching.value = next;
  }
}

function isSummarizing(f) {
  if (launching.value.has(f.id)) return true;
  // Active-jobs rail records also reach us via syncWithRail — but the
  // signal we expose to the UI is just the local launching set plus the
  // absence of a quick_summary on the file. If a job is in-flight from
  // a different tab the rail picks it up; this UI shows a generic
  // "Summarizing…" once we see launching.
  return false;
}

async function remove(f) {
  if (!confirm(t("research_uploads.remove_confirm", { name: f.filename })))
    return;
  try {
    await api.deleteResearchFile(props.companyId, f.id);
    await load();
  } catch (e) {
    error.value = e.message;
  }
}

function kindIcon(k) {
  if (k === "image") return Image;
  if (k === "pdf") return FileText;
  if (k === "pptx" || k === "ppt") return FileImage;
  return FileText;
}

function formatSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatCost(c) {
  if (c == null) return "";
  return `$${Number(c).toFixed(4)}`;
}
</script>

<template>
  <section
    class="bg-surface border border-subtle rounded-card shadow-card p-6"
  >
    <h2 class="font-display text-lg font-semibold text-ink-primary mb-1">
      {{ t("research_uploads.title") }}
    </h2>
    <p class="text-sm text-ink-muted mb-4">
      {{ t("research_uploads.subtitle_prefix") }}
      <span class="font-mono text-ink-secondary">{{ t("research_uploads.subtitle_doc_library") }}</span>
      {{ t("research_uploads.subtitle_suffix") }}
    </p>

    <!-- Drag-drop area -->
    <div
      @drop="onDrop"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      :class="[
        'rounded-lg border-2 border-dashed transition-colors px-6 py-8',
        'flex flex-col items-center justify-center gap-2 cursor-pointer text-center',
        dragOver
          ? 'border-accent bg-accent-soft/40'
          : 'border-subtle bg-surface-muted hover:bg-surface',
      ]"
      @click="fileInput?.click()"
    >
      <UploadCloud
        :class="[
          'h-8 w-8',
          dragOver ? 'text-accent' : 'text-ink-muted',
        ]"
      />
      <div class="text-sm text-ink-primary font-medium">
        {{ t("research_uploads.dropzone") }}
      </div>
      <div class="text-xs text-ink-muted">
        {{ t("research_uploads.size_hint") }}
      </div>
      <input
        ref="fileInput"
        type="file"
        :accept="ACCEPT"
        multiple
        class="hidden"
        @change="onPick"
      />
    </div>

    <div
      v-if="uploadError"
      class="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger flex items-start gap-2"
    >
      <AlertCircle class="h-4 w-4 mt-0.5 shrink-0" />
      <span>{{ uploadError }}</span>
    </div>
    <div
      v-if="uploading"
      class="mt-3 text-xs text-ink-muted inline-flex items-center gap-2"
    >
      <Loader2 class="h-3 w-3 animate-spin" />
      {{ t("research_uploads.uploading") }}
    </div>

    <!-- File list -->
    <div class="mt-6">
      <div
        v-if="loading"
        class="text-sm text-ink-muted inline-flex items-center gap-2"
      >
        <Loader2 class="h-3 w-3 animate-spin" /> {{ t("common.loading") }}
      </div>
      <div
        v-else-if="error"
        class="text-sm text-danger inline-flex items-center gap-2"
      >
        <AlertCircle class="h-4 w-4" />
        {{ error }}
      </div>
      <div
        v-else-if="files.length === 0"
        class="text-sm text-ink-subtle italic"
      >
        {{ t("research_uploads.empty") }}
      </div>
      <ul v-else class="space-y-3">
        <li
          v-for="f in files"
          :key="f.id"
          class="rounded-lg border border-subtle bg-surface-muted px-4 py-3"
        >
          <div class="flex items-start gap-3">
            <component
              :is="kindIcon(f.kind)"
              class="h-4 w-4 mt-0.5 text-ink-muted shrink-0"
            />
            <div class="min-w-0 flex-1">
              <!-- Header row. The whole row toggles expand/collapse, but
                   the EN/中 lang switcher inside has @click.stop so it
                   doesn't also toggle the row. -->
              <div
                @click="
                  f.quick_summary &&
                    !f.quick_summary.error &&
                    toggleExpanded(f.id)
                "
                @keydown.enter.prevent="
                  f.quick_summary &&
                    !f.quick_summary.error &&
                    toggleExpanded(f.id)
                "
                @keydown.space.prevent="
                  f.quick_summary &&
                    !f.quick_summary.error &&
                    toggleExpanded(f.id)
                "
                :role="
                  f.quick_summary && !f.quick_summary.error
                    ? 'button'
                    : undefined
                "
                :tabindex="
                  f.quick_summary && !f.quick_summary.error ? 0 : -1
                "
                :aria-expanded="isExpanded(f.id)"
                :class="[
                  'focus-ring rounded',
                  f.quick_summary && !f.quick_summary.error
                    ? 'cursor-pointer'
                    : 'cursor-default',
                ]"
              >
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm font-medium text-ink-primary truncate">
                    {{ f.filename }}
                  </span>
                  <span
                    class="text-[10px] font-mono uppercase tracking-wide text-ink-muted bg-surface border border-subtle rounded px-1.5 py-px"
                  >
                    {{ f.kind }}
                  </span>
                  <span
                    v-if="sourceLangLabel(f.quick_summary)"
                    class="text-[10px] font-mono uppercase tracking-wide text-accent-ink bg-accent-soft border border-accent-soft rounded px-1.5 py-px"
                    title="Source language detected from the document"
                  >
                    {{ sourceLangLabel(f.quick_summary) }}
                  </span>
                  <span v-if="f.size_bytes" class="text-[10px] text-ink-muted">
                    {{ formatSize(f.size_bytes) }}
                  </span>
                  <span v-if="f.uploaded_at" class="text-[10px] text-ink-subtle ml-auto">
                    {{ new Date(f.uploaded_at).toLocaleString() }}
                  </span>
                  <!-- EN / 中 view-language toggle. Always visible on rows
                       that have bilingual content, so the user can flip
                       the one-liner preview / collapsed view without
                       expanding the row. -->
                  <span
                    v-if="hasBilingualSummary(f.quick_summary)"
                    @click.stop
                    class="inline-flex items-center gap-0.5 text-[10px] shrink-0"
                  >
                    <button
                      type="button"
                      @click="toggleSummaryLang(f.id, 'en')"
                      :class="[
                        'px-1.5 py-0.5 rounded border focus-ring',
                        summaryLangFor(f) === 'en'
                          ? 'bg-accent text-white border-accent'
                          : 'bg-surface text-ink-secondary border-subtle hover:bg-surface-muted',
                      ]"
                    >
                      EN<span
                        v-if="f.quick_summary.language === 'en'"
                        class="opacity-70 ml-0.5"
                        title="Source language"
                      >*</span>
                    </button>
                    <button
                      type="button"
                      @click="toggleSummaryLang(f.id, 'zh')"
                      :class="[
                        'px-1.5 py-0.5 rounded border focus-ring',
                        summaryLangFor(f) === 'zh'
                          ? 'bg-accent text-white border-accent'
                          : 'bg-surface text-ink-secondary border-subtle hover:bg-surface-muted',
                      ]"
                    >
                      中<span
                        v-if="f.quick_summary.language === 'zh'"
                        class="opacity-70 ml-0.5"
                        title="Source language"
                      >*</span>
                    </button>
                  </span>
                  <ChevronUp
                    v-if="f.quick_summary && !f.quick_summary.error && isExpanded(f.id)"
                    class="h-3.5 w-3.5 text-ink-muted shrink-0"
                  />
                  <ChevronDown
                    v-else-if="f.quick_summary && !f.quick_summary.error"
                    class="h-3.5 w-3.5 text-ink-muted shrink-0"
                  />
                </div>
                <!-- Collapsed-state one-liner. Hidden once the user
                     expands (the full summary takes over). -->
                <p
                  v-if="!isExpanded(f.id) && oneLinerFor(f)"
                  class="mt-1 text-xs text-ink-secondary leading-snug line-clamp-2"
                >
                  {{ oneLinerFor(f) }}
                </p>
              </div>

              <!-- In-flight loader (kicked off; waiting on Claude) -->
              <div
                v-if="launching.has(f.id) && !f.quick_summary"
                class="mt-2 text-xs text-ink-muted inline-flex items-center gap-1.5"
              >
                <Loader2 class="h-3 w-3 animate-spin text-accent" />
                <span>{{ t("research_uploads.summarizing_with_rail") }}</span>
              </div>

              <!-- Quick summary block (if present). Collapsed by default —
                   click the filename row to expand. -->
              <div
                v-if="f.quick_summary && !f.quick_summary.error"
                v-show="isExpanded(f.id)"
                class="mt-2 text-xs text-ink-secondary space-y-2"
              >
                <div class="flex items-center gap-2 flex-wrap">
                  <span
                    v-if="titleFor(f)"
                    class="font-medium text-ink-primary"
                  >
                    {{ titleFor(f) }}
                  </span>
                  <span
                    v-if="f.quick_summary.doc_type"
                    class="text-[10px] uppercase tracking-wide font-mono text-accent-ink bg-accent-soft border border-accent-soft rounded px-1.5 py-px"
                  >
                    {{ f.quick_summary.doc_type }}
                  </span>
                </div>

                <!-- Image documents: long bilingual description. -->
                <template
                  v-if="
                    isImage(f) &&
                    (f.quick_summary.description_en ||
                      f.quick_summary.description_zh)
                  "
                >
                  <p
                    v-if="descriptionFor(f)"
                    class="leading-relaxed whitespace-pre-wrap"
                  >
                    {{ descriptionFor(f) }}
                  </p>
                  <p v-else class="text-ink-muted italic">
                    {{ t("research_uploads.no_description_in_lang") }}
                  </p>
                </template>

                <!-- Non-image documents: bilingual summary + bullet list. -->
                <p
                  v-else-if="summaryFor(f)"
                  class="leading-relaxed"
                >
                  {{ summaryFor(f) }}
                </p>
                <ul
                  v-if="keyPointsFor(f).length"
                  class="list-disc pl-4 space-y-0.5"
                >
                  <li
                    v-for="(k, i) in keyPointsFor(f)"
                    :key="`kp-${i}`"
                  >
                    {{ k }}
                  </li>
                </ul>

                <!-- Key figures -->
                <div
                  v-if="(f.quick_summary.key_figures || []).length"
                  class="grid grid-cols-2 sm:grid-cols-3 gap-2"
                >
                  <div
                    v-for="(fig, i) in f.quick_summary.key_figures"
                    :key="`fig-${i}`"
                    class="rounded bg-surface border border-subtle px-2 py-1.5"
                  >
                    <div class="text-[10px] text-ink-muted uppercase tracking-wide">
                      {{ figureLabel(fig, summaryLangFor(f)) }}
                    </div>
                    <div class="text-xs font-medium text-ink-primary font-mono">
                      {{ fig.value }}
                    </div>
                    <div
                      v-if="figureContext(fig, summaryLangFor(f))"
                      class="text-[10px] text-ink-muted mt-0.5 line-clamp-2"
                    >
                      {{ figureContext(fig, summaryLangFor(f)) }}
                    </div>
                  </div>
                </div>

                <!-- Entities -->
                <div
                  v-if="
                    f.quick_summary.entities &&
                    ((f.quick_summary.entities.people || []).length ||
                      (f.quick_summary.entities.organizations || []).length ||
                      (f.quick_summary.entities.products || []).length)
                  "
                  class="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]"
                >
                  <div v-if="(f.quick_summary.entities.people || []).length">
                    <div class="text-ink-muted text-[10px] uppercase tracking-wide mb-0.5">{{ t("research_uploads.people") }}</div>
                    <div class="text-ink-secondary">
                      {{ f.quick_summary.entities.people.join(", ") }}
                    </div>
                  </div>
                  <div v-if="(f.quick_summary.entities.organizations || []).length">
                    <div class="text-ink-muted text-[10px] uppercase tracking-wide mb-0.5">{{ t("research_uploads.orgs") }}</div>
                    <div class="text-ink-secondary">
                      {{ f.quick_summary.entities.organizations.join(", ") }}
                    </div>
                  </div>
                  <div v-if="(f.quick_summary.entities.products || []).length">
                    <div class="text-ink-muted text-[10px] uppercase tracking-wide mb-0.5">{{ t("research_uploads.products_label") }}</div>
                    <div class="text-ink-secondary">
                      {{ f.quick_summary.entities.products.join(", ") }}
                    </div>
                  </div>
                </div>

                <!-- Topics + meta -->
                <div class="flex items-center gap-2 flex-wrap pt-1">
                  <span
                    v-for="topic in f.quick_summary.topics || []"
                    :key="topic"
                    class="text-[10px] text-ink-secondary bg-surface-muted border border-subtle rounded-full px-2 py-0.5"
                  >
                    {{ topic }}
                  </span>
                  <span class="ml-auto flex items-center gap-2 text-[10px] text-ink-muted">
                    <span v-if="f.quick_summary.language">
                      {{ f.quick_summary.language }}
                    </span>
                    <span v-if="f.quick_summary.claude_cost_usd != null">
                      · {{ formatCost(f.quick_summary.claude_cost_usd) }}
                    </span>
                  </span>
                </div>
              </div>

              <div
                v-if="f.quick_summary && f.quick_summary.error"
                class="mt-2 text-xs text-danger inline-flex items-start gap-1"
              >
                <AlertCircle class="h-3 w-3 mt-0.5 shrink-0" />
                <span>{{ f.quick_summary.error }}</span>
              </div>

              <!-- Actions -->
              <div class="mt-3 flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  @click="summarize(f)"
                  :disabled="launching.has(f.id)"
                  :class="[
                    'inline-flex items-center gap-1.5 px-2 py-1 rounded',
                    'text-xs border focus-ring',
                    f.quick_summary && !f.quick_summary.error
                      ? 'border-subtle bg-surface hover:bg-surface-muted text-ink-secondary'
                      : 'border-accent bg-accent text-white hover:bg-accent-hover',
                    launching.has(f.id) && 'opacity-60 cursor-not-allowed',
                  ]"
                >
                  <Loader2
                    v-if="launching.has(f.id)"
                    class="h-3 w-3 animate-spin"
                  />
                  <Sparkles v-else class="h-3 w-3" />
                  <span>
                    {{
                      launching.has(f.id)
                        ? t("research_uploads.btn_summarizing")
                        : f.quick_summary && !f.quick_summary.error
                          ? t("research_uploads.btn_resummarize")
                          : t("research_uploads.btn_quick_summary")
                    }}
                  </span>
                </button>

                <button
                  type="button"
                  @click="previewing = f"
                  class="inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs border border-subtle bg-surface hover:bg-surface-muted text-ink-secondary focus-ring"
                >
                  <Eye class="h-3 w-3" />
                  <span>{{ t("research_uploads.view") }}</span>
                </button>

                <button
                  type="button"
                  @click="remove(f)"
                  class="ml-auto inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs border border-subtle bg-surface hover:bg-danger/10 hover:border-danger/40 hover:text-danger text-ink-muted focus-ring"
                  :title="t('research_uploads.remove_tooltip', { name: f.filename })"
                >
                  <Trash2 class="h-3 w-3" />
                </button>
              </div>

              <div
                v-if="summaryError[f.id]"
                class="mt-2 text-xs text-danger inline-flex items-start gap-1"
              >
                <AlertCircle class="h-3 w-3 mt-0.5 shrink-0" />
                <span>{{ summaryError[f.id] }}</span>
              </div>
            </div>
          </div>
        </li>
      </ul>
    </div>

    <FilePreviewModal
      :company-id="companyId"
      :file="previewing"
      :preview-url="previewUrl"
      :download-url="downloadUrl"
      :previewable-kinds="['pdf', 'image']"
      @close="previewing = null"
    />
  </section>
</template>
