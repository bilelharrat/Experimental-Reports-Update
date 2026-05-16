<script setup>
import { onBeforeUnmount, onMounted, ref, computed } from "vue";
import { useRouter } from "vue-router";
import {
  ArrowLeft,
  FileText,
  Eye,
  Loader2,
  Sparkles,
  Upload,
  AlertCircle,
} from "lucide-vue-next";
import { api } from "../api.js";
import FilePreviewModal from "../components/FilePreviewModal.vue";
import HormuzConsole from "../components/HormuzConsole.vue";

const router = useRouter();

const tab = ref("library"); // "library" | "console"

const MAX_FILES = 10;

const entries = ref([]);
const loadError = ref(null);
const uploading = ref(false);
const uploadErrors = ref([]);
const busyDate = ref(null);
const dragOver = ref(false);
const fileInput = ref(null);
let pollId = null;

async function load() {
  try {
    entries.value = await api.hormuzLibrary();
    loadError.value = null;
  } catch (e) {
    loadError.value = e.message;
  }
}

const anyRunning = computed(() =>
  entries.value.some((e) => {
    const s = e.appendix?.status;
    return s && s !== "complete" && !String(s).startsWith("failed");
  }),
);

// Without a window-level guard, dropping just outside the dropzone makes
// the browser navigate to / open the file — which reads as "drop doesn't
// work". Swallow drops anywhere on this view so only the box acts on them.
function blockWindowDnD(ev) {
  ev.preventDefault();
}

onMounted(() => {
  load();
  // Light poll so in-flight appendix status/stage updates without a manual
  // refresh. Cheap (one JSON call); the Active Jobs rail also tracks it.
  pollId = setInterval(() => {
    if (anyRunning.value || busyDate.value) load();
  }, 4000);
  window.addEventListener("dragover", blockWindowDnD);
  window.addEventListener("drop", blockWindowDnD);
});
onBeforeUnmount(() => {
  if (pollId) clearInterval(pollId);
  window.removeEventListener("dragover", blockWindowDnD);
  window.removeEventListener("drop", blockWindowDnD);
});

async function uploadFiles(files) {
  files = Array.from(files || []);
  if (!files.length || uploading.value) return;
  if (files.length > MAX_FILES) {
    uploadErrors.value = [
      {
        filename: "",
        error: `Too many files (${files.length}). Upload at most ${MAX_FILES} at a time.`,
      },
    ];
    return;
  }
  uploading.value = true;
  uploadErrors.value = [];
  try {
    const res = await api.uploadHormuzSources(files);
    uploadErrors.value = res.errors || [];
    await load();
  } catch (e) {
    uploadErrors.value = [{ filename: "", error: e.message }];
  } finally {
    uploading.value = false;
  }
}

function onPick(ev) {
  uploadFiles(ev.target.files);
  ev.target.value = "";
}

function onDrop(ev) {
  dragOver.value = false;
  uploadFiles(ev.dataTransfer?.files);
}

function onDragOver() {
  dragOver.value = true;
}

function onDragLeave() {
  dragOver.value = false;
}

async function generate(date) {
  busyDate.value = date;
  try {
    await api.generateHormuzAppendix(date);
    await load();
  } catch (e) {
    loadError.value = e.message;
  } finally {
    busyDate.value = null;
  }
}

function appendixState(e) {
  const a = e.appendix || {};
  if (a.complete) return { label: "Appendix ready", tone: "ok" };
  if (!a.status) return { label: "Not generated", tone: "idle" };
  if (String(a.status).startsWith("failed"))
    return { label: a.stage || "Failed", tone: "fail" };
  if (a.status === "complete") return { label: "Appendix ready", tone: "ok" };
  return { label: a.stage || "Generating…", tone: "run" };
}

// PDF preview via the shared modal.
const previewFile = ref(null);
const previewUrl = ref(null);
function openPreview(date, slot, langLabel) {
  previewUrl.value = api.hormuzAppendixFileUrl(date, slot);
  previewFile.value = {
    id: `hormuz-${date}-${slot}`,
    kind: "pdf",
    label: `Hormuz V3 Appendix — ${langLabel} — ${date}`,
    filename: `v3_appendix_${slot}_${date}.pdf`,
  };
}
function closePreview() {
  previewFile.value = null;
  previewUrl.value = null;
}
</script>

<template>
  <div class="max-w-5xl mx-auto px-8 py-10 space-y-6">
    <button
      @click="router.push({ name: 'home' })"
      class="text-sm text-ink-muted hover:text-ink-primary inline-flex items-center gap-1 focus-ring rounded"
    >
      <ArrowLeft class="h-4 w-4" /> Back
    </button>

    <header class="border-b border-subtle pb-4">
      <div class="text-xs uppercase tracking-wider text-ink-muted">
        Hormuz research
      </div>
      <h1 class="font-display text-2xl font-semibold text-ink-primary mt-0.5">
        Source library &amp; V3 appendix
      </h1>
      <p class="mt-1 text-sm text-ink-muted">
        Upload daily reports — the date is read from the filename
        (e.g. <code>中东局势每日研判2026-05-13.pdf</code>). Generate the
        bilingual V3 appendix per date; re-running a date overwrites it.
      </p>
    </header>

    <!-- Tabs -->
    <div class="flex items-center gap-2 border-b border-subtle">
      <button
        v-for="t in [
          { id: 'library', label: 'Source library & V3 appendix' },
          { id: 'console', label: 'Console' },
        ]"
        :key="t.id"
        @click="tab = t.id"
        :class="[
          '-mb-px px-3 py-2 text-sm border-b-2 focus-ring',
          tab === t.id
            ? 'border-accent text-ink-primary font-medium'
            : 'border-transparent text-ink-muted hover:text-ink-primary',
        ]"
      >
        {{ t.label }}
      </button>
    </div>

    <HormuzConsole v-if="tab === 'console'" />

    <template v-else>
    <!-- Upload (click or drag-and-drop, up to 10 files) -->
    <div class="rounded-card border border-subtle bg-surface p-4">
      <div
        role="button"
        tabindex="0"
        @click="fileInput?.click()"
        @keydown.enter.prevent="fileInput?.click()"
        @drop.prevent.stop="onDrop"
        @dragenter.prevent.stop="onDragOver"
        @dragover.prevent.stop="onDragOver"
        @dragleave.prevent="onDragLeave"
        class="flex flex-col items-center justify-center gap-2 px-4 py-8 rounded-lg border-2 border-dashed text-sm cursor-pointer transition-colors focus-ring"
        :class="
          dragOver
            ? 'border-accent bg-accent-soft text-ink-primary'
            : 'border-subtle bg-surface-muted text-ink-muted hover:bg-surface'
        "
      >
        <Loader2 v-if="uploading" class="h-5 w-5 animate-spin text-accent" />
        <Upload v-else class="h-5 w-5" />
        <span class="font-medium text-ink-primary">
          {{
            uploading
              ? "Uploading…"
              : dragOver
                ? "Drop to upload"
                : "Drop source report(s) here, or click to choose"
          }}
        </span>
        <span class="text-xs text-ink-muted">
          Up to {{ MAX_FILES }} files · date is read from each filename
        </span>
        <input
          ref="fileInput"
          type="file"
          multiple
          class="hidden"
          accept=".pdf,.md,.txt,.docx"
          :disabled="uploading"
          @change="onPick"
        />
      </div>
      <ul v-if="uploadErrors.length" class="mt-3 space-y-1">
        <li
          v-for="(er, i) in uploadErrors"
          :key="i"
          class="text-xs text-danger inline-flex items-center gap-1"
        >
          <AlertCircle class="h-3 w-3 shrink-0" />
          <span>{{ er.filename ? er.filename + ": " : "" }}{{ er.error }}</span>
        </li>
      </ul>
    </div>

    <div v-if="loadError" class="text-sm text-danger">{{ loadError }}</div>
    <div
      v-if="!entries.length && !loadError"
      class="text-sm text-ink-muted text-center py-8"
    >
      No source reports yet. Upload one to get started.
    </div>

    <!-- Per-date cards -->
    <div
      v-for="e in entries"
      :key="e.date"
      class="rounded-card border border-subtle bg-surface p-4 space-y-3"
    >
      <div class="flex items-center gap-3">
        <div class="font-display text-lg font-semibold text-ink-primary">
          {{ e.date }}
        </div>
        <span
          v-if="e.previous_date"
          class="text-[11px] text-ink-muted font-mono"
        >
          baseline: {{ e.previous_date }}
        </span>
        <span class="flex-1"></span>
        <span
          class="text-xs px-2 py-0.5 rounded-full"
          :class="{
            'bg-success-soft text-success-ink':
              appendixState(e).tone === 'ok',
            'bg-surface-muted text-ink-muted':
              appendixState(e).tone === 'idle',
            'bg-warning-soft text-warning-ink':
              appendixState(e).tone === 'run',
            'bg-danger-soft text-danger-ink':
              appendixState(e).tone === 'fail',
          }"
        >
          <Loader2
            v-if="appendixState(e).tone === 'run'"
            class="h-3 w-3 inline animate-spin mr-1"
          />
          {{ appendixState(e).label }}
        </span>
      </div>

      <!-- Source files -->
      <div class="flex flex-wrap gap-2">
        <a
          v-for="s in e.sources"
          :key="s.filename"
          :href="api.hormuzSourceUrl(e.date, s.filename)"
          target="_blank"
          rel="noopener"
          class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted hover:bg-surface text-xs text-ink-primary focus-ring"
        >
          <FileText class="h-3.5 w-3.5 text-ink-muted shrink-0" />
          <span class="truncate max-w-[260px]">{{ s.filename }}</span>
          <span class="text-ink-muted"
            >{{ Math.round(s.size_bytes / 1024) }} KB</span
          >
        </a>
      </div>

      <!-- Actions -->
      <div class="flex flex-wrap items-center gap-2 pt-1">
        <button
          type="button"
          :disabled="
            busyDate === e.date || appendixState(e).tone === 'run'
          "
          @click="generate(e.date)"
          class="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-accent text-white text-sm hover:bg-accent-hover focus-ring disabled:opacity-50"
        >
          <Loader2
            v-if="busyDate === e.date || appendixState(e).tone === 'run'"
            class="h-4 w-4 animate-spin"
          />
          <Sparkles v-else class="h-4 w-4" />
          <span>
            {{
              e.appendix?.complete
                ? "Regenerate appendix"
                : "Generate appendix"
            }}
          </span>
        </button>

        <template v-if="e.appendix?.complete">
          <a
            :href="api.hormuzAppendixFileUrl(e.date, 'cn_md')"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-subtle bg-surface-muted hover:bg-surface text-sm text-ink-primary focus-ring"
          >
            <FileText class="h-4 w-4 text-ink-muted" /> CN .md
          </a>
          <button
            type="button"
            @click="openPreview(e.date, 'cn_pdf', '中文')"
            class="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-subtle bg-surface-muted hover:bg-surface text-sm text-ink-primary focus-ring"
          >
            <Eye class="h-4 w-4 text-ink-muted" /> CN PDF
          </button>
          <a
            :href="api.hormuzAppendixFileUrl(e.date, 'en_md')"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-subtle bg-surface-muted hover:bg-surface text-sm text-ink-primary focus-ring"
          >
            <FileText class="h-4 w-4 text-ink-muted" /> EN .md
          </a>
          <button
            type="button"
            @click="openPreview(e.date, 'en_pdf', 'English')"
            class="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-subtle bg-surface-muted hover:bg-surface text-sm text-ink-primary focus-ring"
          >
            <Eye class="h-4 w-4 text-ink-muted" /> EN PDF
          </button>
        </template>
      </div>
    </div>
    </template>

    <FilePreviewModal
      :file="previewFile"
      :preview-url="previewUrl"
      :download-url="previewUrl"
      :previewable-kinds="['pdf']"
      @close="closePreview"
    />
  </div>
</template>
