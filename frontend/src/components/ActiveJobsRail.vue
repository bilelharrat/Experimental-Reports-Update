<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AlertCircle,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Download,
  FileText,
  Globe,
  Languages,
  Loader2,
  MousePointerClick,
  Pencil,
  RefreshCw,
  Search,
  Sparkles,
  Terminal,
} from "lucide-vue-next";
import { useT } from "../i18n.js";
import {
  activeJobs as jobs,
  subscribeActiveJobs,
  unsubscribeActiveJobs,
} from "../activeJobs.js";
import JobLogModal from "./JobLogModal.vue";

const t = useT();
const collapsed = ref(false);
const expandedJobThreads = ref(new Set());
const autoExpandedJobThreads = ref(new Set());
const openJob = ref(null);

// Auto-expand memo threads as they appear. Driven by the shared jobs ref
// instead of a component-local poll.
watch(
  jobs,
  (nextJobs) => {
    const expanded = new Set(expandedJobThreads.value);
    const autoExpanded = new Set(autoExpandedJobThreads.value);
    for (const job of nextJobs) {
      const key = jobKey(job);
      if (
        job.kind === "memo" &&
        hasThreads(job) &&
        !expanded.has(key) &&
        !autoExpanded.has(key)
      ) {
        expanded.add(key);
        autoExpanded.add(key);
      }
    }
    expandedJobThreads.value = expanded;
    autoExpandedJobThreads.value = autoExpanded;
  },
  { immediate: true },
);

onMounted(subscribeActiveJobs);
onBeforeUnmount(unsubscribeActiveJobs);

function pct(j) {
  if (j.kind === "summary" && j.slide_count && j.slide_no) {
    return Math.round((j.slide_no / j.slide_count) * 100);
  }
  if (j.kind === "pdf_translation" && j.page_count && j.page_no) {
    return Math.round((j.page_no / j.page_count) * 100);
  }
  if (
    (j.kind === "public_snapshot_bulk" || j.kind === "company_regen_all") &&
    j.total_count &&
    j.index
  ) {
    return Math.round((j.index / j.total_count) * 100);
  }
  if (j.thread_count) {
    const settled = (j.thread_done_count || 0) + (j.thread_failed_count || 0);
    return Math.round((settled / j.thread_count) * 100);
  }
  return null;
}

function progressText(j) {
  if (j.kind === "summary" && j.slide_count && j.slide_no) {
    return `${j.slide_no}/${j.slide_count}`;
  }
  if (j.kind === "pdf_translation" && j.page_count && j.page_no) {
    return `page ${j.page_no}/${j.page_count}`;
  }
  if (
    (j.kind === "public_snapshot_bulk" || j.kind === "company_regen_all") &&
    j.total_count &&
    j.index
  ) {
    return `${j.index}/${j.total_count}`;
  }
  if (j.thread_count) {
    const settled = (j.thread_done_count || 0) + (j.thread_failed_count || 0);
    const failed = j.thread_failed_count ? `, ${j.thread_failed_count} failed` : "";
    return `${settled}/${j.thread_count} subtasks${failed}`;
  }
  return null;
}

function fmtAge(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return t("jobs.age.seconds", { n: sec });
  if (sec < 3600) return t("jobs.age.minutes", { n: Math.round(sec / 60) });
  return t("jobs.age.hours", { n: Math.round(sec / 3600) });
}

function kindIcon(kind) {
  if (kind === "search") return Search;
  if (kind === "pdf_translation") return Languages;
  if (kind === "summary") return FileText;
  if (kind === "external_research") return FileText;
  if (kind === "research_summary") return Sparkles;
  if (kind === "memo") return Sparkles;
  if (kind === "public_snapshot_bulk") return RefreshCw;
  if (kind === "company_regen_all") return RefreshCw;
  return Sparkles;
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

// Pick an icon for the "latest action" line so a glance tells you whether
// Claude is reading, writing, browsing, or thinking.
function actionIcon(a) {
  if (!a) return null;
  if (a.action === "thinking") return Brain;
  if (a.tool === "WebSearch") return Globe;
  if (a.tool === "WebFetch") return Download;
  if (a.tool === "Read") return FileText;
  if (a.tool === "Write" || a.tool === "Edit") return Pencil;
  if (a.tool === "Bash") return Terminal;
  if (a.action === "result" && a.is_error) return AlertCircle;
  return Sparkles;
}

// Two lines of line-clamp-2 with the rail's font give ~140 chars total
// before the browser ellipses, so we hand the FE a slightly-trimmed
// string and let CSS handle the visual cut.
function actionLine(a) {
  if (!a) return null;
  const trim = (s, n) =>
    s && s.length > n ? s.slice(0, n) + "…" : s || "";
  if (a.action === "thinking") {
    const thought = (a.text || "").replace(/\s+/g, " ").trim();
    return trim(thought, 200) || t("jobs.action.thinking");
  }
  if (a.action === "tool_use") {
    const preview = (a.preview || "").replace(/\s+/g, " ").trim();
    return `${a.tool}: ${trim(preview, 160)}`;
  }
  if (a.action === "tool_result") {
    return `${a.tool} → ${
      a.is_error ? t("jobs.action.tool_error") : t("jobs.action.tool_ok")
    }`;
  }
  if (a.action === "init") return t("jobs.action.claude_initialized");
  if (a.action === "result") {
    if (a.is_error) {
      const status = a.api_error_status ? ` ${a.api_error_status}` : "";
      const message = (a.error || a.text || "").replace(/\s+/g, " ").trim();
      return trim(
        `${t("jobs.modal.job_failed")}${status}${message ? ` - ${message}` : ""}`,
        200,
      );
    }
    return t("jobs.action.run_finished");
  }
  return null;
}

function jobKey(j) {
  return `${j.kind}:${j.job_id || j.report_id || j.file_id || j.item_id || j.title}`;
}

function hasThreads(j) {
  return Array.isArray(j?.threads) && j.threads.length > 0;
}

function sortedThreads(j) {
  return [...(j?.threads || [])].sort((a, b) => {
    const ai = threadPhaseSortIndex(a);
    const bi = threadPhaseSortIndex(b);
    if (ai !== bi) return ai - bi;
    return 0;
  });
}

function threadPhaseSortIndex(thread) {
  const explicit = Number(thread?.phase_index);
  if (Number.isFinite(explicit)) return explicit;
  const match = String(thread?.name || "").match(/^Phase\s+(\d+)/);
  return match ? Number(match[1]) : Number.POSITIVE_INFINITY;
}

function threadsExpanded(j) {
  return expandedJobThreads.value.has(jobKey(j));
}

function toggleThreads(j) {
  const key = jobKey(j);
  const next = new Set(expandedJobThreads.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedJobThreads.value = next;
}

function toolCallText(count) {
  return count === 1
    ? t("jobs.tool_call_one")
    : t("jobs.tool_calls", { count });
}

function threadIcon(thread) {
  if (thread.status === "not_started") return Circle;
  if (thread.status === "done") return CheckCircle2;
  if (thread.status === "failed") return AlertCircle;
  return Loader2;
}

function fmtThreadElapsed(thread) {
  const ms = Number(thread?.elapsed_ms);
  if (!Number.isFinite(ms) || ms < 0) return "";
  const totalS = Math.floor(ms / 1000);
  if (totalS < 60) return `${Math.max(1, Math.round(ms / 1000))}s`;
  const m = Math.floor(totalS / 60);
  const s = totalS % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function jobElapsedText(job) {
  const duration = fmtThreadElapsed({ elapsed_ms: job?.elapsed_ms });
  return duration ? t("jobs.modal.elapsed_duration", { duration }) : "";
}

function fmtThreadEstimate(thread) {
  const ms = Number(thread?.estimate_ms);
  if (!Number.isFinite(ms) || ms <= 0) return "";
  const totalS = Math.floor(ms / 1000);
  const m = Math.floor(totalS / 60);
  const s = totalS % 60;
  const duration = m <= 0 ? `~${totalS}s` : s ? `~${m}m ${s}s` : `~${m}m`;
  return t("jobs.modal.expected_duration", { duration });
}

function threadElapsedText(thread) {
  const elapsed = fmtThreadElapsed(thread);
  if (!elapsed) return "";
  const key =
    thread?.status === "done"
      ? "jobs.modal.actual_duration"
      : "jobs.modal.elapsed_duration";
  return t(key, { duration: elapsed });
}

function threadEventText(thread) {
  if (thread?.status === "not_started") return t("jobs.modal.not_started");
  const count = Number(thread?.event_count || 0);
  if (!count) return "";
  return count === 1
    ? t("jobs.modal.event_count_one")
    : t("jobs.modal.event_count", { count });
}

function open(j) {
  openJob.value = j;
}
function close() {
  openJob.value = null;
}

const visible = computed(() => jobs.value.length > 0);
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="visible"
      class="fixed top-4 right-4 z-40 w-80 max-w-[88vw] flex flex-col gap-2"
    >
      <header
        class="flex items-center gap-2 px-3 py-2 rounded-card bg-surface border border-subtle shadow-card"
      >
        <span class="relative flex h-2 w-2">
          <span
            class="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"
          ></span>
          <span class="relative inline-flex h-2 w-2 rounded-full bg-accent"></span>
        </span>
        <span class="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          {{ t("jobs.rail_title") }} · {{ jobs.length }}
        </span>
        <span class="flex-1"></span>
        <button
          type="button"
          @click="collapsed = !collapsed"
          class="text-ink-muted hover:text-ink-primary text-xs focus-ring rounded inline-flex items-center"
          :title="collapsed ? t('jobs.expand') : t('jobs.collapse')"
        >
          <ChevronRight v-if="collapsed" class="h-3.5 w-3.5" />
          <ChevronDown v-else class="h-3.5 w-3.5" />
        </button>
      </header>

      <ul v-if="!collapsed" class="space-y-2">
        <li
          v-for="j in jobs"
          :key="jobKey(j)"
          class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
        >
          <button
            type="button"
            @click="open(j)"
            class="w-full text-left p-3 hover:bg-surface-muted focus-ring group"
            :title="t('jobs.open_transcript')"
          >
            <div class="flex items-start gap-2">
              <component
                :is="kindIcon(j.kind)"
                class="h-3.5 w-3.5 text-accent mt-0.5 shrink-0"
              />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5">
                  <div class="text-sm font-medium text-ink-primary truncate flex-1">
                    {{ j.title }}
                  </div>
                  <MousePointerClick
                    class="h-3 w-3 text-ink-subtle group-hover:text-accent shrink-0"
                  />
                </div>
                <div class="text-xs text-ink-muted truncate">
                  <span class="font-mono uppercase text-[10px]">{{
                    kindLabel(j.kind)
                  }}</span>
                  <span v-if="j.subtitle" class="text-ink-muted">
                    · {{ j.subtitle }}
                  </span>
                </div>
                <div
                  v-if="j.latest_stage"
                  class="mt-1 text-xs text-ink-secondary line-clamp-2 inline-flex items-center gap-1"
                >
                  <Loader2 class="h-3 w-3 animate-spin shrink-0 text-accent" />
                  <span>{{ j.latest_stage }}</span>
                </div>
                <!-- Latest Claude action — gives the rail a live "stdout"
                     feel without making the user open the modal. -->
                <div
                  v-if="actionLine(j.latest_action)"
                  class="mt-1 text-[11px] text-ink-muted line-clamp-2 inline-flex items-start gap-1 font-mono"
                >
                  <component
                    v-if="actionIcon(j.latest_action)"
                    :is="actionIcon(j.latest_action)"
                    class="h-3 w-3 mt-px shrink-0 opacity-70"
                  />
                  <span>{{ actionLine(j.latest_action) }}</span>
                </div>
                <div
                  v-if="pct(j) != null"
                  class="mt-1.5 h-1 w-full rounded-full bg-surface-muted overflow-hidden"
                >
                  <div
                    class="h-full bg-accent transition-all"
                    :style="{ width: pct(j) + '%' }"
                  ></div>
                </div>
                <div
                  class="mt-1 flex items-center gap-2 text-[10px] text-ink-muted font-mono"
                >
                  <span v-if="progressText(j)">{{ progressText(j) }}</span>
                  <span v-if="j.tool_count">
                    {{ toolCallText(j.tool_count) }}
                  </span>
                  <span v-if="j.claude_cost_usd != null">
                    ${{ Number(j.claude_cost_usd).toFixed(4) }}
                  </span>
                  <span v-if="jobElapsedText(j)" class="tabular-nums">
                    {{ jobElapsedText(j) }}
                  </span>
                  <span v-if="j.last_event_at" class="ml-auto">
                    {{ t("jobs.age_ago", { age: fmtAge(j.last_event_at) }) }}
                  </span>
                </div>
              </div>
            </div>
          </button>
          <div v-if="hasThreads(j)" class="border-t border-subtle bg-canvas/60">
            <button
              type="button"
              @click.stop="toggleThreads(j)"
              class="w-full px-3 py-1.5 flex items-center gap-2 text-left text-[11px] text-ink-muted hover:bg-surface-muted focus-ring"
              :title="threadsExpanded(j) ? t('jobs.collapse') : t('jobs.expand')"
            >
              <ChevronDown v-if="threadsExpanded(j)" class="h-3 w-3 shrink-0" />
              <ChevronRight v-else class="h-3 w-3 shrink-0" />
              <span class="font-mono uppercase tracking-wide">{{
                t("jobs.parallel_flows")
              }}</span>
              <span class="ml-auto font-mono">
                {{ progressText(j) || `${j.threads.length}` }}
              </span>
            </button>
            <ul
              v-if="threadsExpanded(j)"
              class="px-2 pb-2 space-y-1"
              :aria-label="t('jobs.parallel_flows')"
            >
              <li
                v-for="thread in sortedThreads(j)"
                :key="thread.name"
                class="rounded border border-subtle bg-surface px-2 py-1.5"
              >
                <div class="flex items-center gap-1.5 min-w-0">
                  <component
                    :is="threadIcon(thread)"
                    class="h-3 w-3 shrink-0"
                    :class="{
                      'text-success-ink': thread.status === 'done',
                      'text-danger': thread.status === 'failed',
                      'text-accent animate-spin': thread.status === 'running',
                      'text-ink-muted': thread.status === 'not_started',
                    }"
                  />
                  <span class="truncate text-[11px] font-medium text-ink-primary">
                    {{ thread.name }}
                  </span>
                </div>
                <div
                  class="mt-0.5 flex items-center gap-2 pl-4 text-[10px] text-ink-muted font-mono"
                >
                  <span v-if="threadEventText(thread)">{{
                    threadEventText(thread)
                  }}</span>
                  <span v-if="fmtThreadElapsed(thread)" class="tabular-nums">
                    {{ threadElapsedText(thread) }}
                  </span>
                  <span v-if="fmtThreadEstimate(thread)" class="tabular-nums">
                    {{ fmtThreadEstimate(thread) }}
                  </span>
                  <span
                    v-if="thread.latest_action && actionLine(thread.latest_action)"
                    class="truncate"
                  >
                    {{ actionLine(thread.latest_action) }}
                  </span>
                </div>
              </li>
            </ul>
          </div>
        </li>
      </ul>
    </aside>

    <JobLogModal v-if="openJob" :job="openJob" @close="close" />
  </Teleport>
</template>
