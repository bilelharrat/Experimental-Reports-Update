<script setup>
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import {
  Download,
  ExternalLink,
  FileText,
  Presentation,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";

const props = defineProps({
  companyId: { type: String, required: true },
  file: { type: Object, default: null }, // null = closed
});
const emit = defineEmits(["close"]);

const isOpen = computed(() => !!props.file);
const previewUrl = computed(() =>
  props.file ? api.filePreviewUrl(props.companyId, props.file.id) : null,
);
const downloadUrl = computed(() =>
  props.file ? api.fileUrl(props.companyId, props.file.id) : null,
);
const canPreview = computed(() => props.file && props.file.kind === "pdf");

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
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

// Lock body scroll while open.
watch(
  isOpen,
  (open) => {
    if (typeof document !== "undefined") {
      document.body.style.overflow = open ? "hidden" : "";
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
            :is="file?.kind === 'pdf' ? FileText : Presentation"
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
            v-if="canPreview && previewUrl"
            :src="previewUrl"
            class="w-full h-full border-0"
            :title="file?.filename"
          ></iframe>
          <div
            v-else
            class="h-full grid place-items-center text-center px-6"
          >
            <div class="max-w-sm">
              <Presentation class="h-10 w-10 text-ink-muted mx-auto mb-3" />
              <div class="font-display text-lg text-ink-primary">
                In-app preview not available
              </div>
              <p class="mt-1 text-sm text-ink-muted">
                {{ (file?.kind || "this file").toUpperCase() }} files can't be
                rendered directly in the browser yet. Download the file or
                open it in a new tab to view it locally.
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
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
