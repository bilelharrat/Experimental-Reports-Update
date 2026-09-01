<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Download, Loader2, X } from "lucide-vue-next";
import MarkdownIt from "markdown-it";
import { renderAsync } from "docx-preview";
import { useT } from "../i18n.js";

const props = defineProps({
  title: { type: String, default: "" },
  // [{ key, url, kind }] — kind: "docx" | "md" | "text". Multiple sources
  // render as tabs (e.g. a memo's EN / ZH / INTERNAL documents).
  sources: { type: Array, default: () => [] },
});

const emit = defineEmits(["close"]);
const t = useT();

// html: false keeps raw HTML in markdown inert, so v-html below stays safe.
const markdown = new MarkdownIt({ html: false, linkify: true });

const activeIndex = ref(0);
const loading = ref(false);
const loadError = ref(false);
const renderedKind = ref("");
const markdownHtml = ref("");
const textContent = ref("");
const docxContainer = ref(null);

function activeSource() {
  return props.sources[activeIndex.value] || null;
}

async function loadSource() {
  const source = activeSource();
  renderedKind.value = "";
  markdownHtml.value = "";
  textContent.value = "";
  if (docxContainer.value) docxContainer.value.innerHTML = "";
  if (!source?.url) {
    loadError.value = true;
    return;
  }
  loading.value = true;
  loadError.value = false;
  try {
    const response = await fetch(source.url);
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
    activeIndex.value = 0;
    loadSource();
  },
);

function onKeydown(event) {
  if (event.key === "Escape") emit("close");
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
  loadSource();
});
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
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
    >
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
              class="rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase focus-ring"
              :class="
                index === activeIndex
                  ? 'border-accent bg-accent-soft text-accent-ink'
                  : 'border-subtle bg-surface text-ink-muted hover:bg-surface-muted'
              "
              @click="selectSource(index)"
            >
              {{ source.key }}
            </button>
          </div>
        </div>
        <a
          v-if="activeSource()?.url"
          :href="activeSource().url"
          class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
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
      <div class="flex-1 overflow-y-auto bg-surface-muted">
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
