<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
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
const claudeActions = ref([]); // [{action, tool, preview, ...}]
const claudeMeta = ref({ session: null, model: null, cost_usd: null });
const lastThinking = ref(""); // last assistant text block
let eventSource = null;
let watchdogId = null;
let lastEventAt = 0;
let consecutiveErrors = 0;
const NO_EVENT_TIMEOUT_MS = 90_000; // 90s with zero events ⇒ assume dead
const HARD_CEILING_MS = 15 * 60_000; // 15 min total ⇒ give up
let openedAt = 0;

function reset() {
  summary.value = null;
  error.value = null;
  tab.value = "en";
  expandedSet.value = new Set();
  stages.value = [];
  slideEvents.value = [];
  claudeActions.value = [];
  claudeMeta.value = { session: null, model: null, cost_usd: null };
  lastThinking.value = "";
  generating.value = false;
}

function closeStream() {
  if (watchdogId) {
    clearInterval(watchdogId);
    watchdogId = null;
  }
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function failGenerating(message) {
  if (summary.value) return; // already finished — ignore late failures
  closeStream();
  generating.value = false;
  error.value = error.value || message;
}

function openStream() {
  if (!props.file) return;
  closeStream();
  const url = api.fileSummaryStreamUrl(props.companyId, props.file.id);
  eventSource = new EventSource(url);
  openedAt = Date.now();
  lastEventAt = Date.now();
  consecutiveErrors = 0;

  eventSource.onmessage = (msg) => {
    consecutiveErrors = 0;
    lastEventAt = Date.now();
    let entry;
    try {
      entry = JSON.parse(msg.data);
    } catch {
      return;
    }
    handleProgress(entry);
  };
  eventSource.onerror = () => {
    consecutiveErrors++;
    // EventSource readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED.
    // The browser auto-reconnects on transient errors; we only surface
    // when the connection is permanently CLOSED or we've had a run of
    // failed reconnects.
    if (
      eventSource &&
      (eventSource.readyState === 2 || consecutiveErrors >= 5)
    ) {
      failGenerating("Lost connection to summary stream.");
    }
  };

  // Watchdog: if we go too long without ANY event, or we've been
  // generating past the hard ceiling, fail the spinner.
  watchdogId = setInterval(() => {
    if (summary.value) return; // already done
    const idle = Date.now() - lastEventAt;
    const total = Date.now() - openedAt;
    if (idle > NO_EVENT_TIMEOUT_MS) {
      failGenerating(
        `No progress for ${Math.round(idle / 1000)}s — the job appears stuck.`,
      );
    } else if (total > HARD_CEILING_MS) {
      failGenerating(
        `Summary job exceeded ${Math.round(HARD_CEILING_MS / 60000)} min ceiling.`,
      );
    }
  }, 5000);
}

function handleProgress(entry) {
  if (entry.type === "stage") {
    stages.value = [...stages.value, entry];
  } else if (entry.type === "slide_extracted") {
    // Dedupe by slide_no — Claude may emit the same slide twice if it
    // re-writes progress.md.
    const existing = slideEvents.value.find(
      (e) => e.slide_no === entry.slide_no,
    );
    if (existing) {
      Object.assign(existing, entry);
      slideEvents.value = [...slideEvents.value];
    } else {
      slideEvents.value = [...slideEvents.value, entry];
    }
  } else if (entry.type === "claude_action") {
    claudeActions.value = [...claudeActions.value, entry];
    if (entry.action === "init") {
      claudeMeta.value = {
        session: entry.session,
        model: entry.model,
        cost_usd: null,
      };
    } else if (entry.action === "thinking") {
      lastThinking.value = entry.text || "";
    } else if (entry.action === "result") {
      claudeMeta.value = {
        ...claudeMeta.value,
        cost_usd: entry.cost_usd,
        duration_ms: entry.duration_ms,
      };
    }
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

const speed = ref("auto"); // "auto" | "granular" | "fast"

async function startGeneration(forceFresh = false) {
  if (!props.file) return;
  reset();
  generating.value = true;
  // Start the stream subscription BEFORE POSTing so we don't miss early events.
  openStream();
  try {
    await api.generateFileSummary(props.companyId, props.file.id, {
      speed: speed.value,
    });
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

function truncate(s, n) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
}

const actionListRef = ref(null);
watch(
  () => claudeActions.value.length,
  async () => {
    await nextTick();
    if (actionListRef.value) {
      actionListRef.value.scrollTop = actionListRef.value.scrollHeight;
    }
  },
);

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

// Friendly stage labels for the timeline. Order matches the pipeline as
// emitted by the runner; stages we don't see (e.g. uploading on the OpenAI
// fallback) just stay grey.
const STAGE_ORDER = [
  ["starting", "Starting"],
  ["extracting", "Inventorying slides"],
  ["extracted", "Inventory ready"],
  ["claude_starting", "Processing with Claude"],
  ["analyzing", "Analyzing slides"],
  ["translating", "Translating to second language"],
  ["structuring", "Structuring final output"],
  // OpenAI-fallback labels (only show if claude isn't available)
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
  // Latest analyzing event lets us show "Analyzing slide N of M".
  const latestAnalyzing = [...stages.value]
    .reverse()
    .find((s) => s.stage === "analyzing");
  return STAGE_ORDER.map(([key, label], i) => {
    let dynamicLabel = label;
    if (key === "analyzing" && latestAnalyzing?.slide_no) {
      dynamicLabel = latestAnalyzing.slide_count
        ? `Analyzing slide ${latestAnalyzing.slide_no} of ${latestAnalyzing.slide_count}`
        : `Analyzing slide ${latestAnalyzing.slide_no}`;
    }
    return {
      key,
      label: dynamicLabel,
      state: seen.has(key) ? (i < idxLast ? "done" : "active") : "pending",
    };
  });
});

const lastStage = computed(
  () => stages.value[stages.value.length - 1] || null,
);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="sheet-scrim fixed inset-0 z-50 flex items-center justify-center p-4"
      @click.self="emit('close')"
    >
      <div
        class="sheet-panel w-[92vw] h-[92vh] max-w-[1100px] bg-canvas rounded-sheet flex flex-col overflow-hidden"
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
              :class="[ 'text-xs px-2.5 py-1 rounded-md border focus-ring', tab === 'en' ? 'bg-accent text-white border-accent' : 'bg-surface-muted border-subtle text-ink-secondary hover:border-strong', ]"
            >
              English
            </button>
            <button
              type="button"
              @click="tab = 'zh'"
              :class="[ 'text-xs px-2.5 py-1 rounded-md border focus-ring', tab === 'zh' ? 'bg-accent text-white border-accent' : 'bg-surface-muted border-subtle text-ink-secondary hover:border-strong', ]"
            >
              中文
            </button>
          </div>

          <select
            v-model="speed"
            :disabled="generating"
            class="text-xs px-1.5 py-1 rounded border border-subtle bg-surface-muted text-ink-secondary focus-ring disabled:opacity-60"
            title="Generation speed: Auto picks per deck size, Granular reads each page separately (best per-slide visibility), Fast batches 20 pages per read."
          >
            <option value="auto">Auto</option>
            <option value="granular">Granular</option>
            <option value="fast">Fast</option>
          </select>
          <button
            type="button"
            @click="regenerate"
            :disabled="generating"
            class="btn-bordered btn-sm focus-ring inline-flex items-center gap-1.5 disabled:opacity-60"
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
              class="rounded-card bg-surface shadow-card p-5"
            >
              <div
                class="vogue-label mb-3"
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
                    :class="{ 'bg-success-soft text-success-ink': s.state === 'done', 'bg-accent-soft text-accent': s.state === 'active', 'bg-surface-muted text-ink-subtle': s.state === 'pending', }"
                  >
                    <Check v-if="s.state === 'done'" class="h-3 w-3" />
                    <Loader2
                      v-else-if="s.state === 'active'"
                      class="h-3 w-3 animate-spin"
                    />
                    <span v-else class="text-[10px]">·</span>
                  </span>
                  <span
                    :class="s.state === 'pending' ? 'text-ink-subtle' : 'text-ink-secondary'"
                    >{{ s.label }}</span
                  >
                </li>
              </ol>
            </section>

            <!-- Per-slide tickbox feed -->
            <section
              v-if="slideEvents.length"
              class="rounded-card bg-surface shadow-card p-5"
            >
              <div
                class="flex items-center justify-between vogue-label mb-3"
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

            <!-- Claude action feed -->
            <section
              v-if="claudeActions.length"
              class="rounded-card bg-surface shadow-card p-5"
            >
              <div
                class="flex items-center justify-between vogue-label mb-3"
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
                  BSH analyst — live actions
                </span>
                <span
                  v-if="claudeMeta.model"
                  class="font-mono normal-case tracking-normal text-ink-muted"
                  >{{ claudeMeta.model
                  }}<span v-if="claudeMeta.cost_usd != null">
                    · ${{ claudeMeta.cost_usd?.toFixed?.(4) ?? claudeMeta.cost_usd }}</span></span
                >
              </div>
              <ol
                ref="actionListRef"
                class="space-y-1.5 max-h-72 overflow-y-auto text-xs"
              >
                <li
                  v-for="(a, i) in claudeActions"
                  :key="i"
                  class="font-mono"
                >
                  <span
                    v-if="a.action === 'init'"
                    class="text-ink-muted"
                    >▸ analyst online · {{ (a.tools || []).length }} tools available</span
                  >
                  <span
                    v-else-if="a.action === 'thinking'"
                    class="text-ink-secondary"
                  >
                    <span class="text-accent">›</span>
                    <span class="ml-1 italic">{{ truncate(a.text, 220) }}</span>
                  </span>
                  <span
                    v-else-if="a.action === 'tool_use'"
                    class="text-ink-secondary"
                  >
                    <span
                      :class="a.tool === 'Read' ? 'text-info' : a.tool === 'Write' ? 'text-success' : a.tool === 'Edit' ? 'text-warning' : 'text-ink-muted'"
                      >⏻ {{ a.tool }}</span
                    >
                    <span class="ml-1 text-ink-muted">{{ truncate(a.preview, 140) }}</span>
                  </span>
                  <span
                    v-else-if="a.action === 'tool_result'"
                    class="text-ink-subtle"
                  >
                    <span :class="a.is_error ? 'text-danger-ink' : 'text-success'">↩</span>
                    {{ a.is_error ? "error" : "ok" }}
                    <span class="ml-1">{{ truncate(a.preview, 120) }}</span>
                  </span>
                  <span
                    v-else-if="a.action === 'result'"
                    class="text-success-ink"
                  >
                    ✓ analyst done
                    <span v-if="a.duration_ms" class="text-ink-muted">
                      · {{ Math.round(a.duration_ms / 1000) }}s</span
                    >
                  </span>
                </li>
              </ol>
            </section>
          </div>

          <!-- Error state -->
          <div v-else-if="error" class="max-w-2xl mx-auto px-6 py-10">
            <div
              class="banner-danger"
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
                class="vogue-label text-accent mb-3"
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
                  class="vogue-label"
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
