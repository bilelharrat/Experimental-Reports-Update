<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  Download,
  ExternalLink,
  FileText,
  Loader2,
  Maximize2,
  MoveHorizontal,
  RefreshCw,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-vue-next";
import MarkdownIt from "markdown-it";
import { renderAsync } from "docx-preview";
import { RouterLink } from "vue-router";
import { useT } from "../i18n.js";
import { withApiToken } from "../api.js";
import {
  ZOOM_MAX,
  ZOOM_MIN,
  clampZoom,
  docxPageWidth,
  fitZoom,
  nextZoomStep,
} from "../docxFit.js";
import Monogram from "./Monogram.vue";

const props = defineProps({
  title: { type: String, default: "" },
  companyName: { type: String, default: "" },
  companyId: { type: String, default: "" },
  reportId: { type: String, default: "" },
  date: { type: String, default: "" },
  sources: { type: Array, default: () => [] },
  initialKey: { type: String, default: "" },
  allowClose: { type: Boolean, default: false },
});

const emit = defineEmits(["close", "open-fullscreen", "change-source"]);
const t = useT();

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
  if (available > 0) fitValue.value = fitZoom(available, docxPage);
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

const companyLinkTitle = computed(() =>
  props.companyName
    ? `${t("reports.open_company")}: ${props.companyName}`
    : t("reports.open_company"),
);

function activeSource() {
  return props.sources[activeIndex.value] || null;
}

function resolveInitialIndex() {
  if (props.initialKey && props.sources.length) {
    const idx = props.sources.findIndex(
      (s) => s.key.toLowerCase() === props.initialKey.toLowerCase(),
    );
    if (idx >= 0) return idx;
  }
  return 0;
}

async function loadSource() {
  const source = activeSource();
  renderedKind.value = "";
  markdownHtml.value = "";
  textContent.value = "";
  docxPage = 0;
  if (docxContainer.value) docxContainer.value.innerHTML = "";
  if (!source?.url) {
    loadError.value = Boolean(props.sources.length);
    return;
  }
  loading.value = true;
  loadError.value = false;
  try {
    const response = await fetch(withApiToken(source.url));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (source.kind === "docx") {
      const buffer = await response.arrayBuffer();
      renderedKind.value = "docx";
      await nextTick();
      if (docxContainer.value) {
        await renderAsync(buffer, docxContainer.value, undefined, {
          inWrapper: true,
          ignoreLastRenderedPageBreak: true,
        });
        docxPage = docxPageWidth(docxContainer.value.querySelector("section.docx"));
        fitDocx();
      }
    } else if (source.kind === "md") {
      markdownHtml.value = markdown.render(await response.text());
      renderedKind.value = "md";
    } else {
      textContent.value = await response.text();
      renderedKind.value = "text";
    }
    emit("change-source", source);
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

function onFullscreen() {
  emit("open-fullscreen", {
    title: props.title || t("documents.viewer_title"),
    sources: props.sources,
    activeIndex: activeIndex.value,
  });
}

watch(activeIndex, loadSource);
watch(
  () => props.sources,
  () => {
    activeIndex.value = resolveInitialIndex();
    loadSource();
  },
  { deep: true },
);

onMounted(() => {
  activeIndex.value = resolveInitialIndex();
  loadSource();
  // Refit when the viewer changes width: the window, or the reports list
  // hiding and coming back beside it.
  if (typeof ResizeObserver !== "undefined" && scrollArea.value) {
    resizeObserver = new ResizeObserver(fitDocx);
    resizeObserver.observe(scrollArea.value);
  }
});

onBeforeUnmount(() => resizeObserver?.disconnect());
</script>

<template>
  <div class="flex h-full w-full flex-col overflow-hidden bg-surface">
    <!-- One slim bar, so the document gets the height: what it is on the
         left, its controls on the right. -->
    <header class="flex shrink-0 items-center gap-2 border-b border-subtle bg-surface px-3 py-1.5">
      <Monogram
        v-if="companyId || companyName"
        :company="{ id: companyId, name: companyName }"
        :size="20"
        tinted
        class="shrink-0"
      />
      <FileText v-else class="h-4 w-4 shrink-0 text-accent" />
      <h2 class="min-w-0 truncate text-sm font-semibold text-ink-primary" :title="title">
        {{ title || t("reports.viewer_window_title") }}
      </h2>
      <RouterLink
        v-if="companyId"
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
      >
        {{ companyName }}
      </span>
      <span v-if="date" class="shrink-0 whitespace-nowrap text-xs text-ink-muted tabular max-md:hidden">
        · {{ date }}
      </span>

      <!-- Controls: Language Tabs, Download, Fullscreen, Close -->
      <div class="ml-auto flex shrink-0 items-center gap-2">
        <div v-if="sources.length > 1" class="flex items-center gap-1 rounded-full bg-surface-muted p-0.5 border border-subtle">
          <button
            v-for="(source, index) in sources"
            :key="source.key"
            type="button"
            class="rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase transition-colors focus-ring"
            :class="
              index === activeIndex
                ? 'bg-accent text-white shadow-xs'
                : 'text-ink-secondary hover:text-ink-primary'
            "
            @click="selectSource(index)"
          >
            {{ source.key }}
          </button>
        </div>

        <div
          v-if="renderedKind === 'docx' && !loading && !loadError"
          class="flex items-center gap-0.5 rounded-full border border-subtle bg-surface-muted p-0.5"
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

        <a
          v-if="activeSource()?.url"
          :href="withApiToken(activeSource().url)"
          class="inline-flex items-center gap-1.5 rounded border border-subtle bg-surface px-2.5 py-1 text-xs font-medium text-ink-secondary hover:bg-surface-muted hover:text-ink-primary focus-ring"
          :title="t('documents.export')"
        >
          <Download class="h-3.5 w-3.5" />
          <span>{{ t("documents.export") }}</span>
        </a>

        <button
          v-if="sources.length > 0"
          type="button"
          class="inline-flex items-center gap-1 rounded border border-subtle bg-surface p-1.5 text-xs text-ink-muted hover:bg-surface-muted hover:text-ink-primary focus-ring"
          :title="t('reports.open_in_drawer')"
          @click="onFullscreen"
        >
          <Maximize2 class="h-3.5 w-3.5" />
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

    <!-- Document Content Area -->
    <div
      ref="scrollArea"
      class="relative flex-1 overflow-auto bg-surface-muted/30 p-3"
      @wheel="onWheel"
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
          @click="loadSource"
        >
          <RefreshCw class="h-3.5 w-3.5" />
          <span>{{ t("research.retry") }}</span>
        </button>
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
        class="doc-viewer-docx"
        :style="{ zoom: docxZoom }"
        data-testid="viewer-docx"
      ></div>

      <!-- eslint-disable-next-line vue/no-v-html -->
      <div
        v-if="renderedKind === 'md' && !loading && !loadError"
        class="doc-viewer-markdown mx-auto max-w-4xl rounded-card bg-surface p-8 text-sm leading-relaxed text-ink-primary shadow-xs border border-subtle my-2"
        v-html="markdownHtml"
      ></div>

      <pre
        v-if="renderedKind === 'text' && !loading && !loadError"
        class="doc-viewer-text mx-auto max-w-4xl whitespace-pre-wrap rounded-card bg-surface p-6 font-mono text-xs leading-relaxed text-ink-primary shadow-xs border border-subtle my-2"
      >{{ textContent }}</pre>
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
.doc-viewer-markdown :deep(table) {
  border-collapse: collapse;
  margin: 0.8rem 0;
  width: 100%;
}
.doc-viewer-markdown :deep(th),
.doc-viewer-markdown :deep(td) {
  border: 1px solid rgb(0 0 0 / 0.12);
  padding: 0.35rem 0.5rem;
  text-align: left;
}
.doc-viewer-markdown :deep(code) {
  background: rgb(0 0 0 / 0.06);
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
  border-left: 3px solid rgb(0 0 0 / 0.15);
  margin: 0.6rem 0;
  padding-left: 0.8rem;
}
</style>
