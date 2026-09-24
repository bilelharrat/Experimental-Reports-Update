<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ChevronsLeftRight, Download, Flag, Loader2, X } from "lucide-vue-next";
import MarkdownIt from "markdown-it";
import { renderAsync } from "docx-preview";
import { useT } from "../i18n.js";
import { api, withApiToken } from "../api.js";
import { hasPermission, sourceLabel, sourceLanguage } from "../reportStatus.js";
import ReportFlagForm from "./reports/ReportFlagForm.vue";
import {
  loadReportPermissions,
  recordReportDownloaded,
  sessionPermissions,
} from "./reports/reportSession.js";
import { documentHeadings, headingBefore, reportIdFromUrl, selectionIn } from "./reports/docxAnchors.js";

const props = defineProps({
  title: { type: String, default: "" },
  // [{ key, url, kind, label? }] — kind: "docx" | "md" | "text". Multiple
  // sources render as tabs (e.g. a memo's EN / ZH / INTERNAL documents; the
  // internal one is the IC memo and is labelled so).
  sources: { type: Array, default: () => [] },
  // The tab to open on (a viewer handing its current language over).
  initialIndex: { type: Number, default: 0 },
  // The memo these documents belong to. Optional: a memo download URL
  // (/api/reports/<id>/download) names it too. With one, a reader can flag
  // a passage (memo:edit) and Export is an explicit, logged export.
  reportId: { type: String, default: "" },
});

const emit = defineEmits(["close"]);
const t = useT();

// html: false keeps raw HTML in markdown inert, so v-html below stays safe.
const markdown = new MarkdownIt({ html: false, linkify: true });

function clampIndex(index) {
  const max = Math.max(0, props.sources.length - 1);
  return Math.min(max, Math.max(0, Number(index) || 0));
}

const activeIndex = ref(clampIndex(props.initialIndex));
const loading = ref(false);
const loadError = ref(false);
const renderedKind = ref("");
const markdownHtml = ref("");
const textContent = ref("");
const docxContainer = ref(null);

function activeSource() {
  return props.sources[activeIndex.value] || null;
}

const sourceKeys = computed(() => props.sources.map((source) => String(source?.key || "")));

function tabLabel(source) {
  return source?.label || sourceLabel(source?.key, sourceKeys.value, t);
}

// ---- The memo behind the documents ------------------------------------------------

const memoReportId = computed(
  () => props.reportId || reportIdFromUrl(activeSource()?.url) || reportIdFromUrl(props.sources[0]?.url),
);
const canFlag = computed(
  () => Boolean(memoReportId.value) && hasPermission(sessionPermissions.value, "memo:edit"),
);
// A memo's download is an explicit export: gated on memo:export and logged.
const exportHref = computed(() => {
  const url = activeSource()?.url;
  if (!url) return "";
  if (!memoReportId.value || !reportIdFromUrl(url)) return withApiToken(url);
  if (!hasPermission(sessionPermissions.value, "memo:export")) return "";
  return withApiToken(/[?&]purpose=/.test(url) ? url : `${url}${url.includes("?") ? "&" : "?"}purpose=export`);
});

function onExport() {
  const source = activeSource();
  if (memoReportId.value && reportIdFromUrl(source?.url)) {
    recordReportDownloaded(memoReportId.value, sourceLanguage(source?.key), "drawer:docx");
  }
}

async function loadSource() {
  const source = activeSource();
  renderedKind.value = "";
  markdownHtml.value = "";
  textContent.value = "";
  flagButton.value = null;
  if (docxContainer.value) docxContainer.value.innerHTML = "";
  if (!source?.url) {
    loadError.value = true;
    return;
  }
  loading.value = true;
  loadError.value = false;
  try {
    // withApiToken adds the /research prefix when the app is mounted
    // under one; already-prefixed and absolute URLs pass through.
    const response = await fetch(withApiToken(source.url));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (source.kind === "docx") {
      const buffer = await response.arrayBuffer();
      renderedKind.value = "docx";
      await nextTick();
      await renderAsync(buffer, docxContainer.value, undefined, {
        inWrapper: true,
        ignoreLastRenderedPageBreak: true,
      });
    } else if (source.kind === "md") {
      markdownHtml.value = markdown.render(await response.text());
      renderedKind.value = "md";
    } else {
      textContent.value = await response.text();
      renderedKind.value = "text";
    }
  } catch {
    loadError.value = true;
    renderedKind.value = "";
  } finally {
    loading.value = false;
  }
}

function selectSource(index) {
  if (index === activeIndex.value) return;
  activeIndex.value = index;
}

watch(activeIndex, loadSource);
watch(
  () => props.sources,
  () => {
    activeIndex.value = clampIndex(props.initialIndex);
    loadSource();
  },
);

// ---- Flag a passage (G7) --------------------------------------------------------

const flagButton = ref(null); // { x, y, quote, label, language } in viewport px
const flagDraft = ref(null);
const flagBusy = ref(false);
const flagError = ref("");
const flagSent = ref(false);
let flagSentTimer = null;

function onSelectionEnd() {
  if (renderedKind.value !== "docx" || !canFlag.value || flagDraft.value) {
    flagButton.value = null;
    return;
  }
  const found = selectionIn(docxContainer.value);
  if (!found) {
    flagButton.value = null;
    return;
  }
  const rect = typeof found.range.getBoundingClientRect === "function" ? found.range.getBoundingClientRect() : null;
  flagButton.value = {
    x: rect ? rect.left + rect.width / 2 : 80,
    y: rect ? Math.max(8, rect.top - 34) : 80,
    quote: found.quote,
    label: headingBefore(documentHeadings(docxContainer.value), found.range.startContainer),
    language: sourceLanguage(activeSource()?.key),
  };
}

function startFlag() {
  const draft = flagButton.value;
  if (!draft) return;
  flagDraft.value = { quote: draft.quote, label: draft.label, language: draft.language };
  flagButton.value = null;
  flagError.value = "";
  try {
    window.getSelection?.()?.removeAllRanges?.();
  } catch {
    // nothing selected any more
  }
}

async function submitFlag({ flag, note }) {
  const id = memoReportId.value;
  const draft = flagDraft.value;
  if (!id || !draft || flagBusy.value) return;
  flagBusy.value = true;
  flagError.value = "";
  try {
    await api.addReportComment(id, {
      text: note || "",
      kind: draft.label ? "section" : "report",
      label: draft.label || "",
      flag,
      quote: draft.quote,
      ...(draft.language ? { language: draft.language } : {}),
    });
    flagDraft.value = null;
    flagSent.value = true;
    clearTimeout(flagSentTimer);
    flagSentTimer = setTimeout(() => {
      flagSent.value = false;
    }, 2500);
  } catch {
    flagError.value = t("comments.save_failed");
  } finally {
    flagBusy.value = false;
  }
}

function onKeydown(event) {
  if (event.key !== "Escape") return;
  if (flagButton.value || flagDraft.value) {
    flagButton.value = null;
    flagDraft.value = null;
    return;
  }
  emit("close");
}

// ---- Horizontal resize ----------------------------------------------------
// Drag the left edge to resize; double-click it to reset. null = the
// default width (w-full max-w-3xl). The chosen width sticks per browser.

const WIDTH_STORAGE_KEY = "bsh.docViewerWidth";
const MIN_WIDTH = 380;

function loadStoredWidth() {
  try {
    const stored = Number.parseInt(
      localStorage.getItem(WIDTH_STORAGE_KEY) || "",
      10,
    );
    return Number.isFinite(stored) && stored >= MIN_WIDTH ? stored : null;
  } catch {
    return null;
  }
}

const panelWidth = ref(loadStoredWidth());
let resizeStartX = 0;
let resizeStartWidth = 0;

function clampWidth(width) {
  const max = Math.max(MIN_WIDTH, window.innerWidth - 60);
  return Math.min(Math.max(width, MIN_WIDTH), max);
}

function onResizeMove(event) {
  // Dragging left (smaller clientX) widens the right-anchored panel.
  panelWidth.value = clampWidth(
    resizeStartWidth + (resizeStartX - event.clientX),
  );
}

function stopResize() {
  window.removeEventListener("mousemove", onResizeMove);
  window.removeEventListener("mouseup", stopResize);
  document.body.style.removeProperty("cursor");
  document.body.style.removeProperty("user-select");
  if (panelWidth.value) {
    try {
      localStorage.setItem(WIDTH_STORAGE_KEY, String(panelWidth.value));
    } catch {
      // Best-effort persistence only.
    }
  }
}

function startResize(event) {
  resizeStartX = event.clientX;
  resizeStartWidth =
    panelWidth.value ||
    event.currentTarget?.parentElement?.getBoundingClientRect?.().width ||
    768;
  window.addEventListener("mousemove", onResizeMove);
  window.addEventListener("mouseup", stopResize);
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
}

function resetWidth() {
  panelWidth.value = null;
  try {
    localStorage.removeItem(WIDTH_STORAGE_KEY);
  } catch {
    // Best-effort persistence only.
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
  // A selection often ends with the pointer outside the page it started on.
  document.addEventListener("mouseup", onSelectionEnd);
  if (memoReportId.value) loadReportPermissions();
  loadSource();
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown);
  document.removeEventListener("mouseup", onSelectionEnd);
  stopResize();
  clearTimeout(flagSentTimer);
});
</script>

<template>
  <!-- Teleport: an ancestor with a transform/backdrop-filter turns
       position:fixed into "fixed inside that ancestor"; rendering from
       body keeps the drawer glued to the viewport everywhere. -->
  <Teleport to="body">
  <div class="fixed inset-0 z-50" role="dialog" aria-modal="true">
    <div
      class="absolute inset-0 bg-black/30"
      @click="emit('close')"
    ></div>
    <aside
      class="doc-viewer-panel absolute inset-y-0 right-0 flex w-full max-w-3xl flex-col border-l border-subtle bg-surface shadow-card-raised"
      :style="panelWidth ? { width: `${panelWidth}px`, maxWidth: 'none' } : null"
    >
      <button
        type="button"
        class="absolute left-0 top-1/2 z-10 grid h-9 w-9 -translate-x-1/2 -translate-y-1/2 cursor-col-resize place-items-center rounded-full border border-subtle bg-surface text-ink-secondary shadow-card hover:bg-surface-muted hover:text-ink-primary focus-ring"
        role="separator"
        aria-orientation="vertical"
        :aria-label="t('documents.viewer_resize')"
        :title="t('documents.viewer_resize')"
        @mousedown.prevent="startResize"
        @dblclick="resetWidth"
      >
        <ChevronsLeftRight class="h-4 w-4" />
      </button>
      <header class="flex items-center gap-3 border-b border-subtle px-4 py-3">
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-semibold text-ink-primary">
            {{ title || t("documents.viewer_title") }}
          </div>
          <div v-if="sources.length > 1" class="mt-1.5 flex items-center gap-1">
            <button
              v-for="(source, index) in sources"
              :key="source.key"
              type="button"
              class="rounded-full border px-2.5 py-0.5 text-[11px] font-semibold focus-ring"
              :class="
                index === activeIndex
                  ? 'border-accent bg-accent-soft text-accent-ink'
                  : 'border-subtle bg-surface text-ink-muted hover:bg-surface-muted'
              "
              :data-testid="`drawer-source-${String(source.key).toLowerCase()}`"
              @click="selectSource(index)"
            >
              {{ tabLabel(source) }}
            </button>
          </div>
        </div>
        <a
          v-if="exportHref"
          :href="exportHref"
          class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
          data-testid="drawer-export"
          @click="onExport"
        >
          <Download class="h-3.5 w-3.5" />
          {{ t("documents.export") }}
        </a>
        <button
          type="button"
          class="rounded-full p-1.5 text-ink-muted hover:bg-surface-muted focus-ring"
          :aria-label="t('documents.viewer_close')"
          @click="emit('close')"
        >
          <X class="h-4 w-4" />
        </button>
      </header>
      <div
        class="relative flex-1 overflow-y-auto bg-surface-muted"
        data-testid="drawer-scroll"
        @keyup="onSelectionEnd"
        @scroll="flagButton = null"
      >
        <div v-if="flagDraft" class="sticky top-0 z-10 bg-surface-muted/95 p-3">
          <ReportFlagForm
            :quote="flagDraft.quote"
            :section-label="flagDraft.label || ''"
            :language="flagDraft.language || ''"
            :busy="flagBusy"
            :error="flagError"
            @submit="submitFlag"
            @cancel="flagDraft = null"
          />
        </div>
        <div
          v-if="loading"
          class="flex items-center gap-2 p-6 text-sm text-ink-muted"
        >
          <Loader2 class="h-4 w-4 animate-spin" />
          {{ t("documents.viewer_loading") }}
        </div>
        <div
          v-else-if="loadError"
          class="p-6 text-sm text-ink-secondary"
        >
          {{ t("documents.viewer_error") }}
        </div>
        <div
          v-show="renderedKind === 'docx' && !loading"
          ref="docxContainer"
          class="doc-viewer-docx p-4"
        ></div>
        <!-- eslint-disable-next-line vue/no-v-html -- markdown-it runs with html:false, so the output carries no raw HTML from the file -->
        <div
          v-if="renderedKind === 'md'"
          class="doc-viewer-markdown mx-auto max-w-2xl bg-surface p-8 text-sm leading-relaxed text-ink-primary shadow-card my-4 rounded-card"
          v-html="markdownHtml"
        ></div>
        <pre
          v-if="renderedKind === 'text'"
          class="whitespace-pre-wrap p-6 font-mono text-xs text-ink-primary"
          >{{ textContent }}</pre
        >
      </div>
      <button
        v-if="flagButton"
        type="button"
        class="fixed z-[60] inline-flex -translate-x-1/2 items-center gap-1 rounded-full bg-ink-primary px-2.5 py-1 text-caption1 font-semibold text-surface shadow-card-raised focus-ring"
        :style="{ left: `${flagButton.x}px`, top: `${flagButton.y}px` }"
        :title="t('comments.flag_hint')"
        data-testid="drawer-flag-selection"
        @mousedown.prevent
        @click="startFlag"
      >
        <Flag class="h-3 w-3" />
        {{ t("comments.flag") }}
      </button>
      <p
        v-if="flagSent"
        class="pointer-events-none absolute bottom-4 left-1/2 z-20 -translate-x-1/2 rounded-full bg-ink-primary px-3 py-1 text-caption1 font-medium text-surface shadow-card-raised"
        role="status"
        data-testid="drawer-flag-sent"
      >
        {{ t("comments.flag_sent") }}
      </p>
    </aside>
  </div>
  </Teleport>
</template>

<style scoped>
.doc-viewer-panel {
  animation: doc-viewer-slide-in 0.22s ease;
}

@keyframes doc-viewer-slide-in {
  from {
    transform: translateX(100%);
  }
  to {
    transform: translateX(0);
  }
}

/* docx-preview renders page-shaped sections; keep them centered and let
   wide pages scroll inside the drawer instead of clipping. */
.doc-viewer-docx {
  overflow-x: auto;
}
.doc-viewer-docx :deep(.docx-wrapper) {
  background: transparent;
  padding: 0;
}
.doc-viewer-docx :deep(.docx-wrapper > section.docx) {
  margin: 0 auto 1rem;
  box-shadow: 0 1px 4px rgb(0 0 0 / 0.12);
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
.doc-viewer-markdown :deep(table) {
  border-collapse: collapse;
  margin: 0.8rem 0;
  width: 100%;
}
.doc-viewer-markdown :deep(th),
.doc-viewer-markdown :deep(td) {
  border: 1px solid rgb(var(--color-border-subtle));
  padding: 0.35rem 0.5rem;
  text-align: left;
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
  margin: 0.6rem 0;
  padding-left: 0.8rem;
}
</style>
