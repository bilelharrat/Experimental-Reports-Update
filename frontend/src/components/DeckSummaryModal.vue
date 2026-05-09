<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  Languages,
  Loader2,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";

const props = defineProps({
  companyId: { type: String, required: true },
  file: { type: Object, default: null },
});
const emit = defineEmits(["close", "summary-updated"]);

const isOpen = computed(() => !!props.file);
const summary = ref(null);
const error = ref(null);
const tab = ref("en");
const expandedSet = ref(new Set());

// Live progress state
const generating = ref(false);
const stages = ref([]); // [{stage, message, ts}]
const slideEvents = ref([]); // [{slide_no, preview, chars}]
const thinkingTail = ref(""); // last delta tail for the typing ticker
const thinkingChars = ref(0);
let eventSource = null;

function reset() {
  summary.value = null;
  error.value = null;
  tab.value = "en";
  expandedSet.value = new Set();
  stages.value = [];
  slideEvents.value = [];
  thinkingTail.value = "";
  thinkingChars.value = 0;
  generating.value = false;
}

function closeStream() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function openStream() {
  if (!props.file) return;
  closeStream();
  const url = api.fileSummaryStreamUrl(props.companyId, props.file.id);
  eventSource = new EventSource(url);
  eventSource.onmessage = (msg) => {
    let entry;
    try {
      entry = JSON.parse(msg.data);
    } catch {
      return;
    }
    handleProgress(entry);
  };
  eventSource.onerror = () => {
    // Auto-reconnect handled by browser; if it stays errored we'll surface.
  };
}

function handleProgress(entry) {
  if (entry.type === "stage") {
    stages.value = [...stages.value, entry];
  } else if (entry.type === "slide_extracted") {
    slideEvents.value = [...slideEvents.value, entry];
  } else if (entry.type === "thinking") {
    thinkingTail.value = entry.tail || "";
    thinkingChars.value = entry.chars || 0;
  } else if (entry.type === "done") {
    closeStream();
    generating.value = false;
    if (entry.summary) {
      summary.value = entry.summary;
      emit("summary-updated", entry.summary);
    } else {
      // Fall back to fetching from the cache.
      loadCached();
    }
  } else if (entry.type === "error") {
    closeStream();
    generating.value = false;
    error.value = entry.error || "Generation failed";
  }
}

async function loadCached() {
  try {
    summary.value = await api.getFileSummary(props.companyId, props.file.id);
  } catch {
    /* not cached */
  }
}

async function startGeneration(forceFresh = false) {
  if (!props.file) return;
  reset();
  generating.value = true;
  // Start the stream subscription BEFORE POSTing so we don't miss early events.
  openStream();
  try {
    await api.generateFileSummary(props.companyId, props.file.id);
  } catch (e) {
    closeStream();
    generating.value = false;
    error.value = e.message;
  }
}

async function loadOrGenerate() {
  if (!props.file) return;
  reset();
  // Try cached first.
  if (props.file.summary) {
    summary.value = props.file.summary;
    return;
  }
  try {
    summary.value = await api.getFileSummary(props.companyId, props.file.id);
    return;
  } catch {
    // not cached — generate
  }
  await startGeneration();
}

function regenerate() {
  startGeneration(true);
}

function onKey(e) {
  if (e.key === "Escape" && isOpen.value) emit("close");
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  closeStream();
});

watch(
  () => props.file?.id,
  () => {
    if (typeof document !== "undefined") {
      document.body.style.overflow = props.file ? "hidden" : "";
    }
    if (props.file) {
      loadOrGenerate();
    } else {
      closeStream();
      reset();
    }
  },
  { immediate: true },
);

watch(
  () => summary.value?.language,
  (lang) => {
    if (lang === "zh") tab.value = "zh";
    else tab.value = "en";
  },
);

const exec = computed(() => summary.value?.exec_summary?.[tab.value] || "");
const sections = computed(() => summary.value?.sections || []);
const allExpanded = computed(
  () =>
    sections.value.length > 0 &&
    expandedSet.value.size === sections.value.length,
);
function toggleSection(i) {
  const s = new Set(expandedSet.value);
  if (s.has(i)) s.delete(i);
  else s.add(i);
  expandedSet.value = s;
}
function expandAll() {
  expandedSet.value = new Set(sections.value.map((_, i) => i));
}
function collapseAll() {
  expandedSet.value = new Set();
}

function fmtSlideRefs(refs, lang) {
  if (!refs || refs.length === 0) return "";
  const sorted = [...refs].sort((a, b) => a - b);
  const groups = [];
  let start = sorted[0],
    prev = sorted[0];
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === prev + 1) prev = sorted[i];
    else {
      groups.push(start === prev ? `${start}` : `${start}–${prev}`);
      start = sorted[i];
      prev = sorted[i];
    }
  }
  groups.push(start === prev ? `${start}` : `${start}–${prev}`);
  return lang === "zh"
    ? `第 ${groups.join("、")} 页`
    : `Slide${refs.length > 1 ? "s" : ""} ${groups.join(", ")}`;
}

function fmtAge(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)} h ago`;
  return `${Math.round(sec / 86400)} d ago`;
}

const sourceLang = computed(() => {
  const l = summary.value?.language;
  return l === "zh" ? "中文" : l === "en" ? "English" : l || "?";
});

const readingTimeMin = computed(() => {
  const text = exec.value || "";
  if (!text) return 0;
  const words =
    tab.value === "zh"
      ? text.length / 2.5
      : text.split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 220));
});

const fileLabel = computed(
  () => props.file?.label || props.file?.filename || "",
);

// Friendly stage labels for the timeline.
const STAGE_ORDER = [
  ["starting", "Starting"],
  ["extracting", "Extracting slides"],
  ["extracted", "Slides extracted"],
  ["uploading", "Uploading to BSH model"],
  ["uploaded", "Upload complete"],
  ["generating", "BSH model is composing"],
  ["parsing", "Parsing structured output"],
];
const stageStatus = computed(() => {
  const seen = new Set(stages.value.map((s) => s.stage));
  const idxLast = STAGE_ORDER.findIndex(
    ([key]) => key === stages.value[stages.value.length - 1]?.stage,
  );
  return STAGE_ORDER.map(([key, label], i) => ({
    key,
    label,
    state: seen.has(key) ? (i < idxLast ? "done" : "active") : "pending",
  }));
});

const lastStage = computed(
  () => stages.value[stages.value.length - 1] || null,
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
        class="w-[92vw] h-[92vh] max-w-[1100px] bg-canvas rounded-card shadow-card-raised border border-subtle flex flex-col overflow-hidden"
      >
        <!-- Header -->
        <header
          class="flex items-center gap-3 px-5 py-3 border-b border-subtle bg-surface"
        >
          <div
            class="h-8 w-8 rounded-lg bg-accent-soft text-accent grid place-items-center shrink-0"
          >
            <Sparkles class="h-4 w-4" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-ink-primary truncate">
              {{ fileLabel }}
            </div>
            <div
              v-if="summary"
              class="text-xs text-ink-muted truncate flex flex-wrap items-center gap-x-2"
            >
              <span class="font-mono uppercase">{{ summary.language }}</span>
              <span>·</span>
              <span
                >{{ summary.slides_used || summary.slide_count }} slides</span
              >
              <span v-if="summary.mode === 'vision'">
                · <span title="Read visually from the PDF">vision read</span>
              </span>
              <span v-if="summary.generated_at">
                · {{ fmtAge(summary.generated_at) }}</span
              >
            </div>
            <div v-else-if="generating" class="text-xs text-ink-muted truncate">
              {{ lastStage?.message || "Working…" }}
            </div>
            <div v-else class="text-xs text-ink-muted">
              Bilingual summary
            </div>
          </div>

          <div
            v-if="summary"
            class="flex items-center gap-1"
            :title="`Source language: ${sourceLang}`"
          >
            <Languages class="h-3.5 w-3.5 text-ink-muted mr-1" />
            <button
              type="button"
              @click="tab = 'en'"
              :class="[
                'text-xs px-2.5 py-1 rounded-md border focus-ring',
                tab === 'en'
                  ? 'bg-accent text-white border-accent'
                  : 'bg-surface-muted border-subtle text-ink-secondary hover:border-strong',
              ]"
            >
              English
            </button>
            <button
              type="button"
              @click="tab = 'zh'"
              :class="[
                'text-xs px-2.5 py-1 rounded-md border focus-ring',
                tab === 'zh'
                  ? 'bg-accent text-white border-accent'
                  : 'bg-surface-muted border-subtle text-ink-secondary hover:border-strong',
              ]"
            >
              中文
            </button>
          </div>

          <button
            type="button"
            @click="regenerate"
            :disabled="generating"
            class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface-muted text-ink-secondary focus-ring inline-flex items-center gap-1.5 disabled:opacity-60"
            :title="summary ? 'Regenerate summary' : 'Generate summary'"
          >
            <Loader2 v-if="generating" class="h-3 w-3 animate-spin" />
            <RefreshCw v-else class="h-3 w-3" />
            <span>{{
              generating ? "Generating…" : summary ? "Regenerate" : "Generate"
            }}</span>
          </button>
          <button
            type="button"
            @click="emit('close')"
            class="p-1.5 rounded hover:bg-surface-muted text-ink-muted hover:text-ink-primary focus-ring"
            aria-label="Close"
          >
            <X class="h-4 w-4" />
          </button>
        </header>

        <!-- Body -->
        <div class="flex-1 min-h-0 overflow-y-auto">
          <!-- Live progress (generating, no summary yet) -->
          <div
            v-if="generating && !summary"
            class="max-w-3xl mx-auto px-8 py-10 space-y-8"
          >
            <!-- Hero with animated thinking icon -->
            <div class="text-center">
              <div class="relative mx-auto h-14 w-14 mb-4">
                <div
                  class="absolute inset-0 rounded-full bg-accent-soft animate-ping"
                ></div>
                <div
                  class="absolute inset-2 rounded-full bg-accent/20 animate-pulse"
                ></div>
                <div
                  class="relative h-14 w-14 rounded-full bg-accent text-white grid place-items-center"
                >
                  <Sparkles class="h-6 w-6" />
                </div>
              </div>
              <div class="font-display text-xl text-ink-primary">
                Reading the deck
              </div>
              <p class="mt-1 text-sm text-ink-muted">
                Extracting slides, sending to the BSH model, building the
                bilingual summary. Usually 10–25 seconds.
              </p>
            </div>

            <!-- Stage timeline -->
            <section
              class="bg-surface border border-subtle rounded-card shadow-card p-5"
            >
              <div
                class="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-muted mb-3"
              >
                Pipeline
              </div>
              <ol class="space-y-2">
                <li
                  v-for="s in stageStatus"
                  :key="s.key"
                  class="flex items-center gap-3 text-sm"
                >
                  <span
                    class="h-5 w-5 rounded-full grid place-items-center shrink-0"
                    :class="{
                      'bg-success-soft text-success-ink': s.state === 'done',
                      'bg-accent-soft text-accent': s.state === 'active',
                      'bg-surface-muted text-ink-subtle': s.state === 'pending',
                    }"
                  >
                    <Check v-if="s.state === 'done'" class="h-3 w-3" />
                    <Loader2
                      v-else-if="s.state === 'active'"
                      class="h-3 w-3 animate-spin"
                    />
                    <span v-else class="text-[10px]">·</span>
                  </span>
                  <span
                    :class="
                      s.state === 'pending'
                        ? 'text-ink-subtle'
                        : 'text-ink-secondary'
                    "
                    >{{ s.label }}</span
                  >
                </li>
              </ol>
            </section>

            <!-- Per-slide tickbox feed -->
            <section
              v-if="slideEvents.length"
              class="bg-surface border border-subtle rounded-card shadow-card p-5"
            >
              <div
                class="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-muted mb-3"
              >
                <span>Slides extracted</span>
                <span class="font-mono normal-case tracking-normal">
                  {{ slideEvents.length }}
                </span>
              </div>
              <div class="grid grid-cols-8 sm:grid-cols-12 gap-1.5">
                <div
                  v-for="ev in slideEvents"
                  :key="ev.slide_no"
                  :title="`Slide ${ev.slide_no}: ${ev.preview || '(image)'}`"
                  class="h-6 rounded text-[10px] font-mono grid place-items-center bg-success-soft text-success-ink border border-success/20"
                >
                  {{ ev.slide_no }}
                </div>
              </div>
              <div
                v-if="slideEvents.length"
                class="mt-3 text-xs text-ink-muted line-clamp-1 italic"
              >
                {{
                  slideEvents[slideEvents.length - 1].preview ||
                  "(image-only slide)"
                }}
              </div>
            </section>

            <!-- Thinking ticker -->
            <section
              v-if="thinkingChars > 0"
              class="bg-surface border border-subtle rounded-card shadow-card p-5"
            >
              <div
                class="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-muted mb-2"
              >
                <span class="inline-flex items-center gap-1.5">
                  <span class="relative flex h-1.5 w-1.5">
                    <span
                      class="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"
                    ></span>
                    <span
                      class="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent"
                    ></span>
                  </span>
                  BSH model — composing
                </span>
                <span
                  class="font-mono normal-case tracking-normal text-ink-muted"
                  >{{ thinkingChars }} chars</span
                >
              </div>
              <pre
                class="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink-secondary opacity-80 max-h-32 overflow-hidden"
                ><span class="text-ink-subtle">…</span>{{ thinkingTail }}<span class="inline-block w-2 h-3 ml-0.5 bg-accent animate-pulse align-middle"></span></pre>
            </section>
          </div>

          <!-- Error state -->
          <div v-else-if="error" class="max-w-2xl mx-auto px-6 py-10">
            <div
              class="text-sm text-danger-ink bg-danger-soft border border-danger/40 rounded-lg px-3 py-2"
            >
              {{ error }}
            </div>
            <button
              type="button"
              @click="regenerate"
              class="mt-3 text-sm text-accent hover:text-accent-hover focus-ring rounded"
            >
              Try again
            </button>
          </div>

          <!-- Final summary -->
          <article
            v-else-if="summary"
            class="max-w-3xl mx-auto px-8 py-10 space-y-10"
          >
            <section class="relative">
              <div
                class="absolute -left-4 top-0 bottom-0 w-1 rounded-full bg-accent"
              ></div>
              <div
                class="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent mb-3"
              >
                Executive summary
                <span
                  class="text-ink-subtle font-normal normal-case tracking-normal"
                >
                  · ~{{ readingTimeMin }} min read
                </span>
              </div>
              <p
                class="text-ink-primary leading-relaxed text-lg font-display whitespace-pre-wrap"
                :class="tab === 'zh' ? 'tracking-wide' : ''"
              >
                {{ exec }}
              </p>
            </section>

            <section v-if="sections.length">
              <div class="flex items-baseline justify-between mb-3">
                <div
                  class="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-muted"
                >
                  Supporting detail
                  <span
                    class="text-ink-subtle font-normal normal-case tracking-normal"
                  >
                    · {{ sections.length }} sections
                  </span>
                </div>
                <button
                  type="button"
                  @click="allExpanded ? collapseAll() : expandAll()"
                  class="text-xs text-ink-secondary hover:text-ink-primary focus-ring rounded px-1"
                >
                  {{ allExpanded ? "Collapse all" : "Expand all" }}
                </button>
              </div>

              <ol class="space-y-2">
                <li
                  v-for="(s, i) in sections"
                  :key="i"
                  class="bg-surface border border-subtle rounded-card overflow-hidden shadow-card transition-shadow hover:shadow-card-raised"
                >
                  <button
                    type="button"
                    @click="toggleSection(i)"
                    class="w-full flex items-start gap-3 px-4 py-3 hover:bg-surface-muted focus-ring text-left"
                  >
                    <span
                      class="h-6 w-6 rounded-full bg-accent-soft text-accent-ink text-xs font-mono font-semibold grid place-items-center shrink-0 mt-0.5"
                      >{{ i + 1 }}</span
                    >
                    <div class="flex-1 min-w-0">
                      <div
                        class="font-display font-semibold text-ink-primary leading-snug"
                      >
                        {{ s.title?.[tab] }}
                      </div>
                      <div
                        v-if="s.slide_refs && s.slide_refs.length"
                        class="mt-1 flex flex-wrap items-center gap-1 text-[11px]"
                      >
                        <span
                          class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-surface-muted border border-subtle text-ink-muted font-mono"
                        >
                          <Eye class="h-2.5 w-2.5" />
                          {{ fmtSlideRefs(s.slide_refs, tab) }}
                        </span>
                      </div>
                    </div>
                    <ChevronDown
                      v-if="expandedSet.has(i)"
                      class="h-4 w-4 text-ink-muted mt-1 shrink-0"
                    />
                    <ChevronRight
                      v-else
                      class="h-4 w-4 text-ink-muted mt-1 shrink-0"
                    />
                  </button>
                  <div
                    v-if="expandedSet.has(i)"
                    class="px-4 pb-4 pt-1 border-t border-subtle"
                  >
                    <p
                      class="text-ink-secondary leading-relaxed whitespace-pre-wrap"
                      :class="tab === 'zh' ? 'tracking-wide' : ''"
                    >
                      {{ s.body?.[tab] }}
                    </p>
                  </div>
                </li>
              </ol>
            </section>
          </article>
        </div>
      </div>
    </div>
  </Teleport>
</template>
