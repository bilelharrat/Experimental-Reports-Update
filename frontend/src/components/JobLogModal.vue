<script setup>
// Generic Claude-task transcript viewer.
//
// Given a job descriptor `{kind, title, subtitle, log_url, stream_url, ...}`,
// fetches the full event history from /api/jobs/log first, then opens an
// EventSource on stream_url to live-tail any new events. Renders the
// transcript like the inline progress feeds (stage banner + tool-call list)
// and surfaces cost + duration when the result event arrives.

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { apiFetch, withApiToken } from "../api.js";
import {
  AlertCircle,
  ArrowUpRight,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Download,
  Globe,
  Languages,
  Loader2,
  Sparkles,
  X,
} from "lucide-vue-next";

const props = defineProps({
  job: { type: Object, required: true },
});
const emit = defineEmits(["close"]);
const router = useRouter();

function goToResult() {
  if (!props.job.primary_route) return;
  router.push(props.job.primary_route);
  emit("close");
}

const events = ref([]);
const stage = ref(null);
const terminated = ref(false);
const errorText = ref(null);
const finalCost = ref(null);
const finalDuration = ref(null);
const feedRef = ref(null);
let activeStream = null;

// Wall-clock elapsed across the WHOLE job (all sub-sessions / parallel
// threads), not any single run's duration_ms. Ticks once a second while
// the job is live, then freezes at the last event's timestamp.
const nowMs = ref(Date.now());
let clockId = null;

// For composite jobs (memo runs): events carry a `thread` field. The
// modal groups them into per-thread sections so the user can see each
// sub-task's progress independently. Threads are sorted by first-seen
// order. Run-level events (job_init, stage without a thread, done,
// error) get bucketed under the synthetic "main" thread.
const expandedThreads = ref(new Set());

function toggleThread(name) {
  if (expandedThreads.value.has(name)) {
    expandedThreads.value.delete(name);
  } else {
    expandedThreads.value.add(name);
  }
  // Trigger reactivity for Sets.
  expandedThreads.value = new Set(expandedThreads.value);
}

const grouped = computed(() => {
  const groups = new Map();
  const ordered = [];

  function ensure(name) {
    if (!groups.has(name)) {
      groups.set(name, {
        name,
        events: [],
        status: "running", // running | done | failed
        startedAt: null,
        finishedAt: null,
        cost: null,
        duration: null,
        title: name === "main" ? "Run-level events" : name,
      });
      ordered.push(groups.get(name));
    }
    return groups.get(name);
  }

  for (const e of events.value) {
    const name = e.thread || "main";
    const g = ensure(name);
    if (!g.startedAt) g.startedAt = e.ts;
    g.events.push(e);
    if (e.type === "thread_started") g.status = "running";
    else if (e.type === "thread_finished") {
      g.status = "done";
      g.finishedAt = e.ts;
      if (e.cost_usd != null) g.cost = e.cost_usd;
      if (e.duration_ms != null) g.duration = e.duration_ms;
    } else if (e.type === "thread_failed" || e.is_error || e.type === "error") {
      // Only mark a thread failed if the error belongs to it.
      if (e.thread || e.is_error) {
        g.status = "failed";
        if (e.type === "thread_failed") g.finishedAt = e.ts;
      }
    }
  }
  return ordered;
});

// Per-sub-step wall-clock elapsed: (finish ts, or `now` while the step
// is still running, or the step's last event ts once the overall job
// ended) − the step's first event ts. Same clock as totalElapsedMs.
function groupElapsedMs(g) {
  const start = _eventMs({ ts: g.startedAt });
  if (start == null) return null;
  let end;
  if (g.finishedAt) {
    end = _eventMs({ ts: g.finishedAt });
  } else if (g.status === "running" && !terminated.value) {
    end = nowMs.value;
  } else {
    const last = g.events.length ? g.events[g.events.length - 1] : null;
    end = last ? _eventMs(last) : start;
  }
  if (end == null) end = start;
  return Math.max(0, end - start);
}

const isComposite = computed(() =>
  events.value.some((e) => !!e.thread),
);

function ingest(entry) {
  if (entry.type === "stage") {
    stage.value = {
      stage: entry.stage,
      message: entry.message || entry.stage,
      page_no: entry.page_no,
      page_count: entry.page_count,
      slide_no: entry.slide_no,
      slide_count: entry.slide_count,
    };
  } else if (entry.type === "claude_action" && entry.action === "result") {
    if (entry.cost_usd != null) finalCost.value = entry.cost_usd;
    if (entry.duration_ms != null) finalDuration.value = entry.duration_ms;
  } else if (entry.type === "done") {
    terminated.value = true;
  } else if (entry.type === "error") {
    terminated.value = true;
    errorText.value = entry.error || "Job failed";
  }
  events.value.push(entry);
  nextTick(() => {
    const el = feedRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

async function loadHistory() {
  if (!props.job.log_url) return;
  try {
    const res = await apiFetch(props.job.log_url);
    if (!res.ok) return;
    const data = await res.json();
    if (Array.isArray(data)) {
      data.forEach(ingest);
    }
  } catch {
    // ignore — fall through to live-tail
  }
}

function openStream() {
  if (!props.job.stream_url || terminated.value) return;
  activeStream = new EventSource(withApiToken(props.job.stream_url));
  activeStream.onmessage = (msg) => {
    try {
      const entry = JSON.parse(msg.data);
      // De-dup against history we already loaded by checking `ts`.
      if (
        entry.ts &&
        events.value.length &&
        events.value[events.value.length - 1].ts &&
        entry.ts <= events.value[events.value.length - 1].ts &&
        events.value.some((e) => e.ts === entry.ts && e.type === entry.type)
      ) {
        return;
      }
      ingest(entry);
    } catch {
      // ignore
    }
  };
  activeStream.onerror = () => {
    if (terminated.value) closeStream();
  };
}

function closeStream() {
  if (activeStream) {
    activeStream.close();
    activeStream = null;
  }
}

onMounted(async () => {
  clockId = setInterval(() => {
    if (!terminated.value) nowMs.value = Date.now();
  }, 1000);
  await loadHistory();
  if (!terminated.value) openStream();
});
onBeforeUnmount(() => {
  closeStream();
  if (clockId) {
    clearInterval(clockId);
    clockId = null;
  }
});

watch(
  () => props.job.log_url,
  async () => {
    closeStream();
    events.value = [];
    stage.value = null;
    terminated.value = false;
    errorText.value = null;
    finalCost.value = null;
    finalDuration.value = null;
    await loadHistory();
    if (!terminated.value) openStream();
  },
);

function actionIcon(entry) {
  if (entry.type === "stage") return Sparkles;
  if (entry.tool === "WebSearch") return Globe;
  if (entry.tool === "WebFetch") return Download;
  if (entry.action === "thinking") return Brain;
  if (entry.action === "result") return CheckCircle2;
  if (entry.type === "job_init") return Languages;
  if (entry.type === "thread_finished") return CheckCircle2;
  if (entry.type === "thread_failed") return AlertCircle;
  if (entry.type === "thread_started") return Loader2;
  return null;
}

function actionLabel(entry) {
  if (entry.type === "job_init")
    return `${entry.title || "Job"} · ${entry.subtitle || entry.kind || ""}`;
  if (entry.type === "stage") return entry.message || entry.stage;
  if (entry.action === "init")
    return `Claude initialized (${entry.model || "claude"})`;
  if (entry.action === "thinking") return entry.text || "Thinking…";
  if (entry.action === "tool_use")
    return `${entry.tool}: ${entry.preview || ""}`;
  if (entry.action === "tool_result") {
    const status = entry.is_error ? "error" : "ok";
    return `${entry.tool} → ${status}`;
  }
  if (entry.action === "result") {
    const cost = entry.cost_usd
      ? ` ($${Number(entry.cost_usd).toFixed(4)})`
      : "";
    const dur = entry.duration_ms
      ? ` · ${(entry.duration_ms / 1000).toFixed(1)}s`
      : "";
    return `Done${cost}${dur}`;
  }
  if (entry.type === "thread_started")
    return `Started: ${entry.title || entry.thread || "pass"}`;
  if (entry.type === "thread_finished") return "Pass complete";
  if (entry.type === "thread_failed") return "Pass failed";
  if (entry.type === "done") return "Job complete";
  if (entry.type === "error") return `Error: ${entry.error || "?"}`;
  return entry.type;
}

function _eventMs(e) {
  const d = e && e.ts ? Date.parse(e.ts) : NaN;
  return Number.isFinite(d) ? d : null;
}

// Total elapsed = last event ts (or `now` while running) − first event
// ts, spanning every sub-session/thread in the transcript.
const totalElapsedMs = computed(() => {
  const evs = events.value;
  if (!evs.length) return null;
  let first = null;
  for (const e of evs) {
    const t = _eventMs(e);
    if (t != null) {
      first = t;
      break;
    }
  }
  if (first == null) return null;
  let last = null;
  for (let i = evs.length - 1; i >= 0; i--) {
    const t = _eventMs(evs[i]);
    if (t != null) {
      last = t;
      break;
    }
  }
  const end = terminated.value ? (last != null ? last : first) : nowMs.value;
  return Math.max(0, end - first);
});

function fmtElapsed(ms) {
  if (ms == null) return "";
  const totalS = Math.floor(ms / 1000);
  if (totalS < 60) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(totalS / 60);
  const s = totalS % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

const headerSubtitle = computed(() => {
  if (stage.value?.message) return stage.value.message;
  if (terminated.value && errorText.value) return errorText.value;
  if (terminated.value) return "Complete";
  return "Working…";
});
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="emit('close')"
    >
      <div
        class="bg-surface rounded-card shadow-card-raised border border-subtle w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden"
      >
        <header
          class="px-4 py-3 border-b border-subtle flex items-start gap-3"
        >
          <div class="flex-1 min-w-0">
            <div
              class="text-[10px] uppercase tracking-wider text-ink-muted font-mono"
            >
              {{ job.kind }}
            </div>
            <div
              class="text-base font-display font-semibold text-ink-primary truncate"
            >
              {{ job.title }}
            </div>
            <div v-if="job.subtitle" class="text-xs text-ink-muted truncate">
              {{ job.subtitle }}
            </div>
            <div
              class="mt-1 text-xs text-ink-secondary inline-flex items-center gap-1.5"
            >
              <Loader2
                v-if="!terminated"
                class="h-3 w-3 animate-spin text-accent"
              />
              <CheckCircle2
                v-else-if="!errorText"
                class="h-3 w-3 text-success-ink"
              />
              <AlertCircle v-else class="h-3 w-3 text-danger" />
              <span>{{ headerSubtitle }}</span>
            </div>
          </div>
          <button
            type="button"
            @click="emit('close')"
            class="p-1 text-ink-muted hover:text-ink-primary focus-ring rounded"
            title="Close"
          >
            <X class="h-4 w-4" />
          </button>
        </header>

        <div
          ref="feedRef"
          class="flex-1 overflow-y-auto px-3 py-2 space-y-2 font-mono text-[12px] leading-snug bg-canvas"
        >
          <div
            v-if="events.length === 0"
            class="px-2 py-4 text-ink-muted italic"
          >
            Waiting for events…
          </div>

          <!-- Composite job: collapsible per-thread sections. -->
          <template v-if="isComposite">
            <section
              v-for="g in grouped"
              :key="g.name"
              class="rounded border border-subtle bg-surface overflow-hidden"
            >
              <button
                type="button"
                @click="toggleThread(g.name)"
                class="w-full px-2 py-1.5 flex items-center gap-2 text-left hover:bg-surface-muted focus-ring"
              >
                <component
                  :is="
                    g.status === 'done'
                      ? CheckCircle2
                      : g.status === 'failed'
                      ? AlertCircle
                      : Loader2
                  "
                  class="h-3.5 w-3.5 shrink-0"
                  :class="{
                    'text-success-ink': g.status === 'done',
                    'text-danger': g.status === 'failed',
                    'text-accent animate-spin':
                      g.status === 'running' && !terminated,
                    'text-ink-muted': g.status === 'running' && terminated,
                  }"
                />
                <div class="font-semibold text-ink-primary text-[12px] truncate flex-1">
                  {{ g.title }}
                </div>
                <span class="text-[10px] text-ink-muted font-normal">
                  {{ g.events.length }} event{{ g.events.length === 1 ? "" : "s" }}
                </span>
                <span
                  v-if="groupElapsedMs(g) != null"
                  class="text-[10px] text-ink-muted font-normal tabular-nums"
                  :title="'Elapsed for this step'"
                >
                  {{ fmtElapsed(groupElapsedMs(g)) }}
                </span>
                <span
                  v-if="g.cost != null"
                  class="text-[10px] text-ink-muted font-normal"
                >
                  ${{ Number(g.cost).toFixed(4) }}
                </span>
                <ChevronRight
                  v-if="!expandedThreads.has(g.name)"
                  class="h-3 w-3 text-ink-muted"
                />
                <ChevronDown v-else class="h-3 w-3 text-ink-muted" />
              </button>
              <div
                v-if="expandedThreads.has(g.name)"
                class="px-2 py-1 space-y-1 border-t border-subtle bg-canvas"
              >
                <div
                  v-for="(entry, i) in g.events"
                  :key="i"
                  class="flex items-start gap-2 px-2 py-1 rounded"
                  :class="{
                    'bg-accent-soft/30':
                      entry.type === 'stage' || entry.type === 'job_init',
                    'text-danger': entry.is_error || entry.type === 'error',
                    'text-success-ink': entry.type === 'done',
                  }"
                >
                  <component
                    v-if="actionIcon(entry)"
                    :is="actionIcon(entry)"
                    class="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-muted"
                  />
                  <span
                    v-else
                    class="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-muted text-center"
                    >·</span
                  >
                  <div class="min-w-0 flex-1 break-words text-ink-secondary">
                    {{ actionLabel(entry) }}
                  </div>
                </div>
                <!-- End-of-section collapse — live updates auto-scroll to
                     the bottom, so the header is often out of reach.
                     Stays pinned to the bottom of the viewport while the
                     section is on screen. -->
                <button
                  type="button"
                  @click="toggleThread(g.name)"
                  class="sticky bottom-0 w-full mt-1 px-2 py-1 flex items-center justify-center gap-1.5 text-[11px] text-ink-muted hover:text-ink-primary bg-canvas/95 border-t border-subtle focus-ring"
                >
                  <ChevronUp class="h-3 w-3" />
                  Collapse “{{ g.title }}”
                </button>
              </div>
            </section>
          </template>

          <!-- Single-task job: flat event list (existing behavior). -->
          <template v-else>
            <div
              v-for="(entry, i) in events"
              :key="i"
              class="flex items-start gap-2 px-2 py-1 rounded"
              :class="{
                'bg-accent-soft/30':
                  entry.type === 'stage' || entry.type === 'job_init',
                'text-danger': entry.is_error || entry.type === 'error',
                'text-success-ink': entry.type === 'done',
              }"
            >
              <component
                v-if="actionIcon(entry)"
                :is="actionIcon(entry)"
                class="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-muted"
              />
              <span
                v-else
                class="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-muted text-center"
                >·</span
              >
              <div class="min-w-0 flex-1 break-words text-ink-secondary">
                {{ actionLabel(entry) }}
              </div>
            </div>
          </template>
        </div>

        <footer
          class="border-t border-subtle px-4 py-2 flex items-center justify-between gap-3 text-xs text-ink-muted bg-surface-muted"
        >
          <div class="flex items-center gap-3">
            <span v-if="totalElapsedMs != null">
              Elapsed
              <span class="text-ink-primary font-mono">
                {{ fmtElapsed(totalElapsedMs) }}
              </span>
            </span>
            <span v-if="finalCost != null">
              Cost
              <span class="text-ink-primary font-mono">
                ${{ Number(finalCost).toFixed(4) }}
              </span>
            </span>
            <span v-if="finalDuration != null">
              Duration
              <span class="text-ink-primary font-mono">
                {{ (finalDuration / 1000).toFixed(1) }}s
              </span>
            </span>
            <span v-if="!finalCost && !finalDuration && !terminated">
              Live tail · {{ events.length }} event{{
                events.length === 1 ? "" : "s"
              }}
            </span>
          </div>
          <div class="flex items-center gap-2">
            <button
              v-if="job.primary_route"
              type="button"
              @click="goToResult"
              class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface focus-ring text-ink-secondary inline-flex items-center gap-1"
            >
              <ArrowUpRight class="h-3 w-3" />
              View result
            </button>
            <button
              type="button"
              @click="emit('close')"
              class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface focus-ring text-ink-secondary"
            >
              Close
            </button>
          </div>
        </footer>
      </div>
    </div>
  </Teleport>
</template>
