<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  Download,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Loader2,
  Presentation,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";
import { renderMarkdown } from "../markdown.js";

const props = defineProps({
  companyId: { type: String, default: null },
  file: { type: Object, default: null }, // null = closed
  // Callers that don't use the default /api/companies/.../files/.../preview
  // endpoint (e.g. the research-files library, which streams the raw file
  // inline with no server-side conversion) can pass their own URLs here.
  previewUrl: { type: String, default: null },
  downloadUrl: { type: String, default: null },
  // Which `file.kind` values render inline. Research files don't get
  // server-side PPT→PDF conversion, so that caller narrows the set.
  previewableKinds: {
    type: Array,
    default: () => ["pdf", "ppt", "pptx", "image", "md", "markdown"],
  },
});
const emit = defineEmits(["close"]);

const isOpen = computed(() => !!props.file);
const previewUrl = computed(() => {
  if (!props.file) return null;
  if (props.previewUrl) return props.previewUrl;
  if (!props.companyId) return null;
  return api.filePreviewUrl(props.companyId, props.file.id);
});
const downloadUrl = computed(() => {
  if (!props.file) return null;
  if (props.downloadUrl) return props.downloadUrl;
  if (!props.companyId) return null;
  return api.fileUrl(props.companyId, props.file.id);
});
const canPreview = computed(
  () => !!props.file && props.previewableKinds.includes(props.file.kind),
);
const isPpt = computed(() =>
  props.file && (props.file.kind === "ppt" || props.file.kind === "pptx"),
);
const filenameExt = computed(() => {
  const filename = props.file?.filename || props.file?.label || "";
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
});
const isMarkdown = computed(
  () =>
    props.file &&
    (["md", "markdown"].includes(props.file.kind) ||
      (props.file.kind === "text" &&
        [".md", ".markdown"].includes(filenameExt.value))),
);
const markdownHtml = computed(() =>
  isMarkdown.value ? renderMarkdown(previewText.value || "") : "",
);

const previewLoading = ref(false);
const previewError = ref(null);
const previewBlobUrl = ref(null);
const previewText = ref(null);
let abortCtl = null;

function clearBlob() {
  if (previewBlobUrl.value) {
    URL.revokeObjectURL(previewBlobUrl.value);
    previewBlobUrl.value = null;
  }
  previewText.value = null;
}

async function loadPreview() {
  clearBlob();
  previewError.value = null;
  if (!canPreview.value || !previewUrl.value) return;
  if (abortCtl) abortCtl.abort();
  abortCtl = new AbortController();
  previewLoading.value = true;
  try {
    const res = await fetch(previewUrl.value, { signal: abortCtl.signal });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        if (j?.detail) detail = j.detail;
      } catch {
        // not JSON, ignore
      }
      previewError.value = detail;
      return;
    }
    if (isMarkdown.value) {
      previewText.value = await res.text();
      return;
    }
    const blob = await res.blob();
    previewBlobUrl.value = URL.createObjectURL(blob);
  } catch (e) {
    if (e.name !== "AbortError") {
      previewError.value = e.message || String(e);
    }
  } finally {
    previewLoading.value = false;
  }
}

function fmtSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function onKey(e) {
  if (e.key === "Escape" && isOpen.value) emit("close");
}

onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  if (abortCtl) abortCtl.abort();
  clearBlob();
});

// Lock body scroll while open + (re)load preview when file changes.
watch(
  () => props.file,
  (f) => {
    if (typeof document !== "undefined") {
      document.body.style.overflow = f ? "hidden" : "";
    }
    if (f) {
      loadPreview();
    } else {
      if (abortCtl) abortCtl.abort();
      clearBlob();
      previewError.value = null;
      previewLoading.value = false;
    }
  },
  { immediate: true },
);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
      @click.self="emit('close')"
    >
      <div
        class="w-[90vw] h-[90vh] max-w-[1400px] bg-surface rounded-card shadow-card-raised border border-subtle flex flex-col overflow-hidden"
      >
        <header
          class="flex items-center gap-3 px-4 py-2.5 border-b border-subtle bg-surface"
        >
          <component
            :is="
              file?.kind === 'image'
                ? ImageIcon
                : file?.kind === 'ppt' || file?.kind === 'pptx'
                  ? Presentation
                  : FileText
            "
            class="h-4 w-4 text-ink-muted shrink-0"
          />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-ink-primary truncate">
              {{ file?.label || file?.filename }}
            </div>
            <div class="text-xs text-ink-muted truncate">
              <span class="uppercase">{{ file?.kind }}</span>
              <span> · {{ fmtSize(file?.size_bytes) }}</span>
              <span v-if="file?.language">
                · {{ (file.language || "en").toUpperCase() }}</span
              >
              <span v-if="isPpt && previewBlobUrl" class="ml-1 text-ink-subtle">
                · converted to PDF
              </span>
            </div>
          </div>
          <a
            v-if="canPreview"
            :href="previewUrl"
            target="_blank"
            rel="noopener"
            class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface-muted text-ink-secondary inline-flex items-center gap-1.5 focus-ring"
          >
            <ExternalLink class="h-3 w-3" /> New tab
          </a>
          <a
            :href="downloadUrl"
            :download="file?.filename"
            class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface-muted text-ink-secondary inline-flex items-center gap-1.5 focus-ring"
          >
            <Download class="h-3 w-3" /> Download
          </a>
          <button
            type="button"
            @click="emit('close')"
            class="p-1.5 rounded hover:bg-surface-muted text-ink-muted hover:text-ink-primary focus-ring"
            aria-label="Close preview"
          >
            <X class="h-4 w-4" />
          </button>
        </header>

        <div class="flex-1 min-h-0 bg-surface-muted">
          <iframe
            v-if="previewBlobUrl"
            :src="previewBlobUrl"
            class="w-full h-full border-0"
            :title="file?.filename"
          ></iframe>

          <div
            v-else-if="isMarkdown && previewText !== null"
            class="h-full overflow-auto bg-surface"
          >
            <article
              class="md-body max-w-4xl mx-auto px-6 py-6 text-sm text-ink-primary"
              v-html="markdownHtml"
            ></article>
          </div>

          <div
            v-else-if="previewLoading"
            class="h-full grid place-items-center text-center px-6"
          >
            <div class="max-w-sm">
              <Loader2 class="h-8 w-8 text-accent mx-auto mb-3 animate-spin" />
              <div class="font-display text-lg text-ink-primary">
                {{ isPpt ? "Generating preview…" : "Loading preview…" }}
              </div>
              <p v-if="isPpt" class="mt-1 text-sm text-ink-muted">
                Microsoft PowerPoint is converting this deck to PDF on the
                server. First conversion can take 10–30 seconds; subsequent
                opens are instant from cache.
              </p>
            </div>
          </div>

          <div
            v-else-if="previewError || !canPreview"
            class="h-full grid place-items-center text-center px-6"
          >
            <div class="max-w-md">
              <Presentation class="h-10 w-10 text-ink-muted mx-auto mb-3" />
              <div class="font-display text-lg text-ink-primary">
                Preview not available
              </div>
              <p class="mt-1 text-sm text-ink-muted">
                {{ previewError || "This file type can't be previewed." }}
              </p>
              <div class="mt-4 inline-flex gap-2">
                <a
                  :href="downloadUrl"
                  :download="file?.filename"
                  class="px-3 py-1.5 rounded-lg bg-accent text-white text-sm hover:bg-accent-hover focus-ring inline-flex items-center gap-1.5"
                >
                  <Download class="h-3.5 w-3.5" />
                  Download
                </a>
                <button
                  v-if="canPreview"
                  type="button"
                  @click="loadPreview"
                  class="px-3 py-1.5 rounded-lg border border-subtle text-sm text-ink-secondary hover:bg-surface focus-ring"
                >
                  Retry
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
