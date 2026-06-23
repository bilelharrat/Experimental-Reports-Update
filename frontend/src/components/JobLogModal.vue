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
import { useT } from "../i18n.js";
import {
  AlertCircle,
  ArrowUpRight,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Circle,
  Download,
  FileText,
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
const t = useT();

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
        orderIndex: ordered.length,
        events: [],
        status: "running", // running | done | failed
        plannedAt: null,
        startedAt: null,
        finishedAt: null,
        cost: null,
        duration: null,
        description: null,
        estimateMs: null,
        phaseIndex: null,
        pendingToolUses: 0,
        sawToolActivity: false,
        title: name === "main" ? t("jobs.modal.run_level_events") : name,
      });
      ordered.push(groups.get(name));
    }
    return groups.get(name);
  }

  for (const e of events.value) {
    const name = e.thread || "main";
    const g = ensure(name);
    if (e.type === "thread_planned") {
      g.status = "not_started";
      g.plannedAt = e.ts;
      g.description = e.description || g.description;
      g.estimateMs = e.estimate_ms ?? g.estimateMs;
      g.phaseIndex = e.phase_index ?? g.phaseIndex;
      g.title = e.title || e.thread || g.title;
    } else if (!g.startedAt) {
      g.startedAt = e.ts;
    }
    g.events.push(e);
    if (e.type === "thread_started") {
      g.status = "running";
      g.startedAt = e.ts;
    }
    else if (e.type === "thread_finished") {
      g.status = "done";
      g.finishedAt = e.ts;
      if (e.cost_usd != null) g.cost = e.cost_usd;
      if (e.duration_ms != null) g.duration = e.duration_ms;
    } else if (e.type === "thread_failed" || e.type === "error") {
      // Only mark a thread failed if the error belongs to it.
      if (e.thread || e.type === "error") {
        g.status = "failed";
        if (e.type === "thread_failed") g.finishedAt = e.ts;
      }
    } else if (e.type === "claude_action" && e.thread) {
      if (e.action === "tool_use") {
        g.sawToolActivity = true;
        g.pendingToolUses += 1;
        g.status = "running";
        g.finishedAt = null;
      } else if (e.action === "tool_result") {
        g.sawToolActivity = true;
        g.pendingToolUses = Math.max(0, g.pendingToolUses - 1);
        if (e.is_error) {
          g.status = "failed";
          g.finishedAt = e.ts;
        } else if (
          g.pendingToolUses === 0 &&
          g.sawToolActivity &&
          !isPhaseGroup(g)
        ) {
          // Memo pass rows often have enough signal to settle before the
          // whole Claude subprocess emits its final result.
          g.status = "done";
          g.finishedAt = e.ts;
        }
      } else if (e.is_error) {
        g.status = "failed";
        g.finishedAt = e.ts;
      }
    }
  }
  return [...ordered].sort((a, b) => {
    if (a.name === "main") return -1;
    if (b.name === "main") return 1;
    const ai = phaseSortIndex(a);
    const bi = phaseSortIndex(b);
    if (ai !== bi) return ai - bi;
    return a.orderIndex - b.orderIndex;
  });
});

function isPhaseGroup(g) {
  return g?.phaseIndex != null || /^Phase \d+\s+-/.test(String(g?.name || ""));
}

function phaseSortIndex(g) {
  if (!isPhaseGroup(g)) return Number.POSITIVE_INFINITY;
  const explicit = Number(g?.phaseIndex);
  if (Number.isFinite(explicit)) return explicit;
  const match = String(g?.name || "").match(/^Phase\s+(\d+)/);
  return match ? Number(match[1]) : Number.POSITIVE_INFINITY;
}

// Per-sub-step wall-clock elapsed: (finish ts, or `now` while the step
// is still running, or the step's last event ts once the overall job
// ended) − the step's first event ts. Same clock as totalElapsedMs.
function groupElapsedMs(g) {
  if (g.status === "not_started") return null;
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
    errorText.value = entry.error || t("jobs.modal.job_failed");
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
  if (entry.type === "thread_planned") return Circle;
  if (entry.tool === "WebSearch") return Globe;
  if (entry.tool === "WebFetch") return Download;
  if (entry.action === "thinking") return Brain;
  if (entry.action === "result") return entry.is_error ? AlertCircle : CheckCircle2;
  if (entry.type === "job_init") {
    if (entry.kind === "pdf_translation") return Languages;
    return FileText;
  }
  if (entry.type === "thread_finished") return CheckCircle2;
  if (entry.type === "thread_failed") return AlertCircle;
  if (entry.type === "thread_started") return Loader2;
  return null;
}

function kindLabel(kind) {
  if (kind?.startsWith("console_")) return t("jobs.kind.console");
  const key = {
    search: "jobs.kind.search",
    pdf_translation: "jobs.kind.pdf_translation",
    summary: "jobs.kind.summary",
    external_research: "jobs.kind.external_research",
    research_summary: "jobs.kind.research_summary",
    serena_research_task: "jobs.kind.serena_research_task",
    serena_analysis_tool: "jobs.kind.serena_analysis_tool",
    memo: "jobs.kind.memo",
    public_snapshot: "jobs.kind.public_snapshot",
    public_snapshot_bulk: "jobs.kind.public_snapshot_bulk",
    company_regen_all: "jobs.kind.company_regen_all",
  }[kind];
  return key ? t(key) : kind || t("jobs.kind.task");
}

function actionLabel(entry) {
  if (entry.type === "job_init")
    return `${entry.title || t("jobs.modal.job")} · ${
      entry.subtitle || entry.kind || ""
    }`;
  if (entry.type === "stage") return entry.message || entry.stage;
  if (entry.action === "init")
    return `${t("jobs.action.claude_initialized")} (${entry.model || "claude"})`;
  if (entry.action === "thinking") return entry.text || t("jobs.action.thinking");
  if (entry.action === "tool_use")
    return `${entry.tool}: ${entry.preview || ""}`;
  if (entry.action === "tool_result") {
    const status = entry.is_error
      ? t("jobs.action.tool_error")
      : t("jobs.action.tool_ok");
    return `${entry.tool} → ${status}`;
  }
  if (entry.action === "rate_limit") {
    const resetTime = fmtFriendlyDateTime(entry.resets_at);
    return resetTime
      ? t("jobs.modal.rate_limit_reset", { time: resetTime })
      : t("jobs.modal.rate_limit");
  }
  if (entry.action === "result") {
    if (entry.is_error) {
      const status = entry.api_error_status ? ` ${entry.api_error_status}` : "";
      const message = entry.error || entry.text || entry.preview || "";
      return `${t("jobs.modal.job_failed")}${status}${message ? ` - ${message}` : ""}`;
    }
    const cost = entry.cost_usd
      ? ` ($${Number(entry.cost_usd).toFixed(4)})`
      : "";
    const dur = entry.duration_ms
      ? ` · ${(entry.duration_ms / 1000).toFixed(1)}s`
      : "";
    return `${t("jobs.action.run_finished")}${cost}${dur}`;
  }
  if (entry.type === "thread_started")
    return t("jobs.modal.started", {
      title: entry.title || entry.thread || t("jobs.modal.pass"),
    });
  if (entry.type === "thread_planned")
    return t("jobs.modal.planned", {
      title: entry.title || entry.thread || t("jobs.modal.pass"),
    });
  if (entry.type === "thread_finished") return t("jobs.modal.pass_complete");
  if (entry.type === "thread_failed") return t("jobs.modal.pass_failed");
  if (entry.type === "done") return t("jobs.modal.job_complete");
  if (entry.type === "error")
    return t("jobs.modal.error", { error: entry.error || "?" });
  return entry.type;
}

function eventDetailLines(entry) {
  const lines = [];
  if (entry.description) {
    lines.push(entry.description);
  }
  if (entry.estimate_ms) {
    lines.push(
      `${t("jobs.modal.estimate")}: ${fmtElapsed(Number(entry.estimate_ms))}`,
    );
  }
  if (entry.api_error_status) {
    lines.push(`provider_status: ${entry.api_error_status}`);
  }
  if (entry.error && entry.action !== "result") {
    lines.push(`error: ${entry.error}`);
  }
  if (Array.isArray(entry.contract_errors) && entry.contract_errors.length) {
    lines.push(...entry.contract_errors.map((err) => `check: ${err}`));
  }
  if (Array.isArray(entry.expected_files) && entry.expected_files.length) {
    for (const file of entry.expected_files) {
      const status = file.exists ? "found" : "missing";
      const path = file.path || file.label || "unknown path";
      lines.push(`${file.label || "file"}: ${status} · ${path}`);
    }
  }
  if (
    Array.isArray(entry.generated_renderer_scripts) &&
    entry.generated_renderer_scripts.length
  ) {
    lines.push(
      ...entry.generated_renderer_scripts.map((path) => `blocked: ${path}`),
    );
  }
  return lines;
}

function visibleEvents(entries) {
  return entries.filter((entry) => entry.type !== "output_piece");
}

function outputPieces(entries) {
  return entries.filter((entry) => entry.type === "output_piece");
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function fmtStartedTimestamp(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return [
    d.getFullYear(),
    pad2(d.getMonth() + 1),
    pad2(d.getDate()),
  ].join("-") + ` ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

function fmtFriendlyDateTime(value) {
  if (!value) return "";
  let dateValue = value;
  if (typeof value === "number" || /^\d+(\.\d+)?$/.test(String(value))) {
    const numeric = Number(value);
    dateValue = numeric > 1_000_000_000_000 ? numeric : numeric * 1000;
  }
  const d = new Date(dateValue);
  if (Number.isNaN(d.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(d);
}

function outputStartedText(entry) {
  const timestamp = fmtStartedTimestamp(entry.started_at || entry.ts);
  return timestamp
    ? t("jobs.modal.output_started", { timestamp })
    : t("jobs.modal.output_started_unknown");
}

function outputFileText(entry) {
  return entry.filename || entry.path || entry.artifact || t("jobs.modal.output_piece");
}

function outputTruncatedText(entry) {
  const count = Number(entry.content_chars);
  return t("jobs.modal.output_truncated", {
    count: Number.isFinite(count) ? count.toLocaleString() : "?",
  });
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
  if (terminated.value && errorText.value) return errorText.value;
  if (stage.value?.message) return stage.value.message;
  if (terminated.value) return t("jobs.modal.complete");
  return t("jobs.modal.working");
});

function eventCountText(count) {
  return count === 1
    ? t("jobs.modal.event_count_one")
    : t("jobs.modal.event_count", { count });
}

function activityEventCount(g) {
  return g.events.filter(
    (event) => event.type !== "thread_planned" && event.type !== "output_piece",
  ).length;
}

function groupStatusText(g) {
  if (g.status === "not_started") return t("jobs.modal.not_started");
  if (g.status === "done") return t("jobs.modal.complete");
  if (g.status === "failed") return t("jobs.modal.pass_failed");
  return null;
}

function estimateText(g) {
  const ms = Number(g?.estimateMs);
  if (!Number.isFinite(ms) || ms <= 0) return "";
  return t("jobs.modal.expected_duration", {
    duration: `~${fmtElapsed(ms)}`,
  });
}

function groupElapsedText(g) {
  const ms = groupElapsedMs(g);
  if (ms == null) return "";
  const key =
    g.status === "done"
      ? "jobs.modal.actual_duration"
      : "jobs.modal.elapsed_duration";
  return t(key, { duration: fmtElapsed(ms) });
}

function liveTailText(count) {
  return count === 1
    ? t("jobs.modal.live_tail_one")
    : t("jobs.modal.live_tail", { count });
}
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
              {{ kindLabel(job.kind) }}
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
            :title="t('jobs.modal.close')"
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
            {{ t("jobs.modal.waiting") }}
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
                      : g.status === 'not_started'
                      ? Circle
                      : Loader2
                  "
                  class="h-3.5 w-3.5 shrink-0"
                  :class="{
                    'text-success-ink': g.status === 'done',
                    'text-danger': g.status === 'failed',
                    'text-ink-muted': g.status === 'not_started',
                    'text-accent animate-spin':
                      g.status === 'running' && !terminated,
                    'text-ink-muted': g.status === 'running' && terminated,
                  }"
                />
                <div class="font-semibold text-ink-primary text-[12px] truncate flex-1">
                  {{ g.title }}
                </div>
                <span
                  v-if="groupStatusText(g)"
                  class="text-[10px] text-ink-muted font-normal"
                >
                  {{ groupStatusText(g) }}
                </span>
                <span class="text-[10px] text-ink-muted font-normal">
                  {{ eventCountText(activityEventCount(g)) }}
                </span>
                <span
                  v-if="estimateText(g)"
                  class="text-[10px] text-ink-muted font-normal tabular-nums"
                  :title="t('jobs.modal.estimate_title')"
                >
                  {{ estimateText(g) }}
                </span>
                <span
                  v-if="groupElapsedMs(g) != null"
                  class="text-[10px] text-ink-muted font-normal tabular-nums"
                  :title="t('jobs.modal.elapsed_title')"
                >
                  {{ groupElapsedText(g) }}
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
                  v-for="(entry, i) in visibleEvents(g.events)"
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
                    <div
                      v-if="eventDetailLines(entry).length"
                      class="mt-1 space-y-0.5 text-[11px] text-ink-muted"
                    >
                      <div
                        v-for="line in eventDetailLines(entry)"
                        :key="line"
                        class="font-mono"
                      >
                        {{ line }}
                      </div>
                    </div>
                  </div>
                </div>
                <div
                  v-if="outputPieces(g.events).length"
                  class="mt-2 pt-2 border-t border-subtle"
                >
                  <div
                    class="px-2 text-[10px] uppercase tracking-wide text-ink-muted"
                  >
                    {{ t("jobs.modal.output_section") }}
                  </div>
                  <article
                    v-for="(entry, i) in outputPieces(g.events)"
                    :key="`output-${i}`"
                    class="mt-1 rounded border border-subtle bg-surface px-2 py-2"
                  >
                    <div
                      class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-ink-muted"
                    >
                      <span>{{ outputStartedText(entry) }}</span>
                      <span v-if="entry.phase">
                        {{ t("jobs.modal.output_phase", { phase: entry.phase }) }}
                      </span>
                      <span :title="entry.path || outputFileText(entry)">
                        {{ outputFileText(entry) }}
                      </span>
                    </div>
                    <pre
                      class="mt-1 max-h-96 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-snug text-ink-secondary font-mono"
                    >{{ entry.content }}</pre>
                    <div
                      v-if="entry.truncated"
                      class="mt-1 text-[10px] text-ink-muted"
                    >
                      {{ outputTruncatedText(entry) }}
                    </div>
                  </article>
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
                  {{ t("jobs.modal.collapse_step", { title: g.title }) }}
                </button>
              </div>
            </section>
          </template>

          <!-- Single-task job: flat event list (existing behavior). -->
          <template v-else>
            <div
              v-for="(entry, i) in visibleEvents(events)"
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
                <div
                  v-if="eventDetailLines(entry).length"
                  class="mt-1 space-y-0.5 text-[11px] text-ink-muted"
                >
                  <div
                    v-for="line in eventDetailLines(entry)"
                    :key="line"
                    class="font-mono"
                  >
                    {{ line }}
                  </div>
                </div>
              </div>
            </div>
            <div
              v-if="outputPieces(events).length"
              class="mt-2 pt-2 border-t border-subtle"
            >
              <div
                class="px-2 text-[10px] uppercase tracking-wide text-ink-muted"
              >
                {{ t("jobs.modal.output_section") }}
              </div>
              <article
                v-for="(entry, i) in outputPieces(events)"
                :key="`output-${i}`"
                class="mt-1 rounded border border-subtle bg-surface px-2 py-2"
              >
                <div
                  class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-ink-muted"
                >
                  <span>{{ outputStartedText(entry) }}</span>
                  <span v-if="entry.phase">
                    {{ t("jobs.modal.output_phase", { phase: entry.phase }) }}
                  </span>
                  <span :title="entry.path || outputFileText(entry)">
                    {{ outputFileText(entry) }}
                  </span>
                </div>
                <pre
                  class="mt-1 max-h-96 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-snug text-ink-secondary font-mono"
                >{{ entry.content }}</pre>
                <div
                  v-if="entry.truncated"
                  class="mt-1 text-[10px] text-ink-muted"
                >
                  {{ outputTruncatedText(entry) }}
                </div>
              </article>
            </div>
          </template>
        </div>

        <footer
          class="border-t border-subtle px-4 py-2 flex items-center justify-between gap-3 text-xs text-ink-muted bg-surface-muted"
        >
          <div class="flex items-center gap-3">
            <span v-if="totalElapsedMs != null">
              {{ t("jobs.modal.elapsed") }}
              <span class="text-ink-primary font-mono">
                {{ fmtElapsed(totalElapsedMs) }}
              </span>
            </span>
            <span v-if="finalCost != null">
              {{ t("jobs.modal.cost") }}
              <span class="text-ink-primary font-mono">
                ${{ Number(finalCost).toFixed(4) }}
              </span>
            </span>
            <span v-if="finalDuration != null">
              {{ t("jobs.modal.duration") }}
              <span class="text-ink-primary font-mono">
                {{ (finalDuration / 1000).toFixed(1) }}s
              </span>
            </span>
            <span v-if="!finalCost && !finalDuration && !terminated">
              {{ liveTailText(events.length) }}
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
              {{ t("jobs.modal.view_result") }}
            </button>
            <button
              type="button"
              @click="emit('close')"
              class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface focus-ring text-ink-secondary"
            >
              {{ t("jobs.modal.close") }}
            </button>
          </div>
        </footer>
      </div>
    </div>
  </Teleport>
</template>
