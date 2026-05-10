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
import {
  ArrowUpRight,
  Brain,
  CheckCircle2,
  Download,
  Globe,
  Languages,
  Loader2,
  Sparkles,
  X,
  AlertCircle,
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
    const res = await fetch(props.job.log_url);
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
  activeStream = new EventSource(props.job.stream_url);
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
  await loadHistory();
  if (!terminated.value) openStream();
});
onBeforeUnmount(closeStream);

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
  if (entry.type === "done") return "Job complete";
  if (entry.type === "error") return `Error: ${entry.error || "?"}`;
  return entry.type;
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
          class="flex-1 overflow-y-auto px-3 py-2 space-y-1 font-mono text-[12px] leading-snug bg-canvas"
        >
          <div
            v-if="events.length === 0"
            class="px-2 py-4 text-ink-muted italic"
          >
            Waiting for events…
          </div>
          <div
            v-for="(entry, i) in events"
            :key="i"
            class="flex items-start gap-2 px-2 py-1 rounded"
            :class="{
              'bg-accent-soft/30': entry.type === 'stage' || entry.type === 'job_init',
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
        </div>

        <footer
          class="border-t border-subtle px-4 py-2 flex items-center justify-between gap-3 text-xs text-ink-muted bg-surface-muted"
        >
          <div class="flex items-center gap-3">
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
