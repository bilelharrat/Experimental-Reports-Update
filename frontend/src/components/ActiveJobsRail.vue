<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from "vue";
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
  Terminal,
} from "lucide-vue-next";
import AiMark from "./AiMark.vue";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import {
  activeJobs as jobs,
  refreshActiveJobs,
  subscribeActiveJobs,
  unsubscribeActiveJobs,
} from "../activeJobs.js";
import JobLogModal from "./JobLogModal.vue";

const props = defineProps({
  copilotOpen: { type: Boolean, default: false },
});

const openCopilot = inject("openCopilot", null);
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
  if (kind === "pdf_translation") return Languages;
  if (kind === "summary") return FileText;
  if (kind === "external_research") return FileText;
  if (kind === "public_snapshot_bulk") return RefreshCw;
  if (kind === "company_regen_all") return RefreshCw;
  return AiMark;
}

function kindLabel(kind) {
  if (kind?.startsWith("console_")) return t("jobs.kind.console");
  const key = {
    search: "jobs.kind.search",
    pdf_translation: "jobs.kind.pdf_translation",
    summary: "jobs.kind.summary",
    external_research: "jobs.kind.external_research",
    research_summary: "jobs.kind.research_summary",
    research_analysis: "jobs.kind.research_analysis",
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
  return null;
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

function diagnoseJob(job) {
  if (!openCopilot || !job?.company_id) return;
  openCopilot({
    companyId: job.company_id,
    prompt: `Diagnose this failed job: ${job.title}. What broke and what should I do next?`,
    context: {
      surface: "jobs",
      job: {
        kind: job.kind,
        title: job.title,
        detail: job.error || job.subtitle || "",
        company_id: job.company_id,
      },
    },
  });
}

function jobFailed(job) {
  return String(job?.status || "").toLowerCase().includes("fail")
    || job?.thread_failed_count > 0;
}

// ---- Cancel ----------------------------------------------------------------
// Kinds with a cancel endpoint; each entry returns the API call for a row,
// or null when the row lacks the identifiers.
function cancelCall(job) {
  switch (job?.kind) {
    case "memo":
      return job.report_id ? () => api.cancelReportRun(job.report_id) : null;
    case "serena_research_task":
      return job.company_id && job.task_id
        ? () => api.memoAnalysis.cancelTask(job.company_id, job.task_id)
        : null;
    case "console_ask":
      return job.company_id && job.session_id && job.turn_id
        ? () => api.console.cancelAsk(job.company_id, job.session_id, job.turn_id)
        : null;
    case "research_summary":
      return job.company_id && job.file_id
        ? () => api.cancelResearchFileSummary(job.company_id, job.file_id)
        : null;
    case "research_analysis":
      return job.company_id && job.file_id
        ? () => api.cancelResearchFileAnalysis(job.company_id, job.file_id)
        : null;
    case "external_research":
      return job.item_id
        ? () => api.cancelExternalResearchAnalysis(job.item_id)
        : null;
    case "pdf_translation":
      return job.item_id
        ? () => api.cancelExternalTranslation(job.item_id)
        : null;
    case "stock_tracker":
      return job.tracker_id && job.run_id
        ? () => api.stockResearch.cancelRun(job.tracker_id, job.run_id)
        : null;
    case "stock_aggregate":
      return job.period_id
        ? () => api.stockResearch.cancelAggregate(job.period_id)
        : null;
    case "stock_strategy":
      return job.period_id
        ? () => api.stockResearch.cancelStrategyMap(job.period_id)
        : null;
    default:
      return null;
  }
}

const cancelArmedKey = ref("");
const cancellingKey = ref("");
let cancelDisarmTimer = null;
onBeforeUnmount(() => clearTimeout(cancelDisarmTimer));

function cancelLabel(job) {
  const key = jobKey(job);
  if (cancellingKey.value === key) return t("jobs.cancelling");
  if (cancelArmedKey.value === key) return t("jobs.cancel_confirm");
  return t("jobs.cancel");
}

async function requestCancel(job) {
  const key = jobKey(job);
  if (cancellingKey.value) return;
  // Two-step confirmation: the first click arms, the second (within 4s)
  // actually cancels a paid run.
  if (cancelArmedKey.value !== key) {
    cancelArmedKey.value = key;
    clearTimeout(cancelDisarmTimer);
    cancelDisarmTimer = setTimeout(() => {
      cancelArmedKey.value = "";
    }, 4000);
    return;
  }
  clearTimeout(cancelDisarmTimer);
  cancelArmedKey.value = "";
  const call = cancelCall(job);
  if (!call) return;
  cancellingKey.value = key;
  try {
    await call();
  } catch {
    // 404/409: the job already finished — the refresh below clears it.
  } finally {
    cancellingKey.value = "";
    await refreshActiveJobs();
  }
}

const visible = computed(() => jobs.value.length > 0);
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="visible"
      :class="[
        'fixed top-[60px] z-20 w-[22rem] max-w-[92vw] flex flex-col transition-[right] duration-200 ease-out',
        props.copilotOpen ? 'max-xl:hidden rail-beside-copilot' : 'right-3',
      ]"
    >
      <div class="glass-panel glass-popover relative flex max-h-[min(32rem,calc(100vh-5rem))] flex-col rounded-[18px]">
        <header class="flex shrink-0 items-center gap-2 px-3.5 py-2.5">
          <AiMark class="h-5 w-5 shrink-0" />
          <span class="text-footnote font-semibold text-ink-primary">
            {{ t("jobs.rail_title") }}
          </span>
          <span class="chip bg-info-soft text-info-ink tabular">{{ jobs.length }}</span>
          <span class="flex-1"></span>
          <button
            type="button"
            @click="collapsed = !collapsed"
            class="icon-btn !h-7 !w-7"
            :title="collapsed ? t('jobs.expand') : t('jobs.collapse')"
            :aria-label="collapsed ? t('jobs.expand') : t('jobs.collapse')"
          >
            <ChevronDown
              class="h-3.5 w-3.5 transition-transform duration-200"
              :class="collapsed ? '-rotate-90' : ''"
            />
          </button>
        </header>

        <ul
          v-if="!collapsed"
          class="min-h-0 space-y-1.5 overflow-y-auto overscroll-contain px-2 pb-2"
        >
          <li
            v-for="j in jobs"
            :key="jobKey(j)"
            class="overflow-hidden rounded-[13px] bg-surface/80 shadow-card"
          >
            <button
              type="button"
              @click="open(j)"
              class="group w-full p-3 text-left transition-colors hover:bg-ink-primary/[0.025] focus-ring"
              :title="t('jobs.open_transcript')"
            >
              <div class="flex items-start gap-2.5">
                <span class="job-row-icon !bg-info-soft !text-info-ink">
                  <component :is="kindIcon(j.kind)" class="h-3.5 w-3.5" />
                </span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-1.5">
                    <div class="min-w-0 flex-1 truncate text-footnote font-semibold text-ink-primary">
                      {{ j.title }}
                    </div>
                    <MousePointerClick
                      class="h-3 w-3 shrink-0 text-ink-subtle group-hover:text-accent"
                    />
                  </div>
                  <div class="truncate text-caption1 text-ink-muted">
                    <span>{{ kindLabel(j.kind) }}</span>
                    <span v-if="j.subtitle"> · {{ j.subtitle }}</span>
                  </div>
                  <div
                    v-if="j.report_ready"
                    class="mt-1.5 inline-flex flex-wrap items-center gap-1.5 text-caption1"
                  >
                    <span class="chip bg-success-soft text-success-ink">
                      <CheckCircle2 class="h-3 w-3 shrink-0" />
                      {{ t("jobs.done") }}
                    </span>
                    <span class="text-ink-secondary">{{
                      t("jobs.finalizing_artifacts")
                    }}</span>
                  </div>
                  <div
                    v-else-if="j.latest_stage"
                    class="mt-1.5 inline-flex items-center gap-1 text-caption1 text-ink-secondary line-clamp-2"
                  >
                    <Loader2 class="h-3 w-3 shrink-0 animate-spin text-info" />
                    <span>{{ j.latest_stage }}</span>
                  </div>
                  <!-- Latest Claude action — gives the rail a live "stdout"
                       feel without making the user open the modal. -->
                  <div
                    v-if="actionLine(j.latest_action)"
                    class="mt-1 inline-flex items-start gap-1 font-mono text-[11px] text-ink-muted line-clamp-2"
                  >
                    <component
                      v-if="actionIcon(j.latest_action)"
                      :is="actionIcon(j.latest_action)"
                      class="mt-px h-3 w-3 shrink-0 opacity-70"
                    />
                    <span>{{ actionLine(j.latest_action) }}</span>
                  </div>
                  <div
                    v-if="pct(j) != null"
                    class="mt-2 h-1 w-full overflow-hidden rounded-full bg-ink-primary/[0.08]"
                  >
                    <div
                      class="progress-fill h-full rounded-full transition-all"
                      :style="{ width: pct(j) + '%' }"
                    ></div>
                  </div>
                  <div
                    class="mt-1.5 flex items-center gap-2 text-caption2 text-ink-muted tabular"
                  >
                    <span v-if="progressText(j)">{{ progressText(j) }}</span>
                    <span v-if="j.tool_count">
                      {{ toolCallText(j.tool_count) }}
                    </span>
                    <span v-if="j.claude_cost_usd != null">
                      ${{ Number(j.claude_cost_usd).toFixed(4) }}
                    </span>
                    <span v-if="jobElapsedText(j)">
                      {{ jobElapsedText(j) }}
                    </span>
                    <span v-if="j.last_event_at" class="ml-auto">
                      {{ t("jobs.age_ago", { age: fmtAge(j.last_event_at) }) }}
                    </span>
                  </div>
                </div>
              </div>
            </button>
            <button
              v-if="jobFailed(j) && j.company_id && openCopilot"
              type="button"
              class="hairline-t w-full px-3 py-2 text-left text-caption1 font-medium text-accent-ink transition-colors hover:bg-accent/[0.06] focus-ring"
              @click.stop="diagnoseJob(j)"
            >
              {{ t("copilot.action_diagnose_job") }}
            </button>
            <button
              v-if="cancelCall(j) && !jobFailed(j) && !j.report_ready"
              type="button"
              class="hairline-t w-full px-3 py-2 text-left text-caption1 font-medium transition-colors focus-ring"
              :class="
                cancelArmedKey === jobKey(j)
                  ? 'text-danger hover:bg-danger/10'
                  : 'text-ink-muted hover:bg-ink-primary/[0.04]'
              "
              :disabled="cancellingKey === jobKey(j)"
              @click.stop="requestCancel(j)"
            >
              {{ cancelLabel(j) }}
            </button>
            <div v-if="hasThreads(j)" class="hairline-t bg-ink-primary/[0.02]">
              <button
                type="button"
                @click.stop="toggleThreads(j)"
                class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-caption1 text-ink-muted transition-colors hover:bg-ink-primary/[0.04] focus-ring"
                :title="threadsExpanded(j) ? t('jobs.collapse') : t('jobs.expand')"
              >
                <ChevronDown
                  class="h-3 w-3 shrink-0 transition-transform duration-200"
                  :class="threadsExpanded(j) ? '' : '-rotate-90'"
                />
                <span class="font-medium">{{
                  t("jobs.parallel_flows")
                }}</span>
                <span class="ml-auto tabular">
                  {{ progressText(j) || `${j.threads.length}` }}
                </span>
              </button>
              <ul
                v-if="threadsExpanded(j)"
                class="space-y-1 px-2 pb-2"
                :aria-label="t('jobs.parallel_flows')"
              >
                <li
                  v-for="thread in sortedThreads(j)"
                  :key="thread.name"
                  class="rounded-[9px] bg-surface px-2 py-1.5 shadow-card"
                >
                  <div class="flex min-w-0 items-center gap-1.5">
                    <component
                      :is="threadIcon(thread)"
                      class="h-3 w-3 shrink-0"
                      :class="{ 'text-success-ink': thread.status === 'done', 'text-danger': thread.status === 'failed', 'text-info animate-spin': thread.status === 'running', 'text-ink-muted': thread.status === 'not_started', }"
                    />
                    <span class="truncate text-[11px] font-medium text-ink-primary">
                      {{ thread.name }}
                    </span>
                  </div>
                  <div
                    class="mt-0.5 flex items-center gap-2 pl-4 text-[10px] text-ink-muted tabular"
                  >
                    <span v-if="threadEventText(thread)">{{
                      threadEventText(thread)
                    }}</span>
                    <span v-if="fmtThreadElapsed(thread)">
                      {{ threadElapsedText(thread) }}
                    </span>
                    <span v-if="fmtThreadEstimate(thread)">
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
      </div>
    </aside>

    <JobLogModal v-if="openJob" :job="openJob" @close="close" />
  </Teleport>
</template>
