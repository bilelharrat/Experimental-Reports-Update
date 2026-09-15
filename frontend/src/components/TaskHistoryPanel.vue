<script setup>
import { onMounted, ref } from "vue";
import {
  Brain,
  CheckCircle2,
  FileText,
  Globe,
  History,
  Languages,
  Terminal,
  TrendingUp,
  X,
  XCircle,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import JobLogModal from "./JobLogModal.vue";

const props = defineProps({
  copilotOpen: { type: Boolean, default: false },
});
defineEmits(["close"]);

const t = useT();
const rows = ref([]);
const loading = ref(true);
const loadFailed = ref(false);
const openJob = ref(null);

async function load() {
  loading.value = true;
  loadFailed.value = false;
  try {
    const data = await api.listJobHistory(30);
    rows.value = Array.isArray(data) ? data : [];
  } catch {
    loadFailed.value = true;
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function kindIcon(kind) {
  const k = String(kind || "");
  if (k === "memo" || k === "hormuz" || k === "summary") return FileText;
  if (k === "search" || k === "external_research") return Globe;
  if (k === "pdf_translation") return Languages;
  if (k.startsWith("console")) return Terminal;
  if (k.startsWith("stock") || k === "weekly_stocks" || k.startsWith("public_snapshot"))
    return TrendingUp;
  return Brain;
}

function kindLabel(kind) {
  const k = String(kind || "");
  if (!k) return t("jobs.kind.task");
  if (k.startsWith("console_")) return t("jobs.kind.console");
  const key = `jobs.kind.${k}`;
  const label = t(key);
  return label === key ? k.replaceAll("_", " ") : label;
}

// A memo row enriched from the report record knows better than the raw
// terminal event whether the run ultimately delivered.
function outcome(row) {
  const status = String(row.status || "");
  if (status.startsWith("complete")) return "done";
  if (status.startsWith("failed")) return "failed";
  if (status === "awaiting_studio") return "done";
  const terminal = String(row.terminal_type || "");
  if (terminal === "done" || terminal === "recovered") return "done";
  if (terminal === "cancelled") return "cancelled";
  return "failed";
}

function outcomeLabel(row) {
  const o = outcome(row);
  if (o === "done") return t("jobs.done");
  if (o === "cancelled") return t("jobs.status_cancelled");
  return t("jobs.status_failed");
}

function fmtDuration(ms) {
  const sec = Math.round(Number(ms) / 1000);
  if (!Number.isFinite(sec) || sec < 0) return "";
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ${sec % 60}s`;
  return `${Math.floor(min / 60)}h ${min % 60}m`;
}

function fmtAge(ts) {
  const then = Date.parse(ts);
  if (!Number.isFinite(then)) return "";
  const sec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (sec < 60) return t("jobs.age.seconds", { n: sec });
  if (sec < 3600) return t("jobs.age.minutes", { n: Math.round(sec / 60) });
  if (sec < 86400) return t("jobs.age.hours", { n: Math.round(sec / 3600) });
  return new Date(then).toLocaleDateString();
}

// Memo runs with the report-ready detach carry both timestamps: how long
// until the report was readable, and until the whole run (artifacts
// included) ended.
function timingLine(row) {
  const started = Date.parse(row.started_at);
  const ready = Date.parse(row.report_ready_at);
  const finished = Date.parse(row.run_finished_at);
  if (
    Number.isFinite(started) &&
    Number.isFinite(ready) &&
    Number.isFinite(finished) &&
    finished - ready > 15000
  ) {
    return t("jobs.history_report_ready", {
      ready: fmtDuration(ready - started),
      total: fmtDuration(finished - started),
    });
  }
  const elapsed = Number.isFinite(started) && Number.isFinite(finished)
    ? finished - started
    : row.elapsed_ms;
  const text = fmtDuration(elapsed);
  return text ? t("jobs.history_took", { duration: text }) : "";
}

function open(row) {
  if (!row.log_url && !row.primary_route) return;
  openJob.value = {
    kind: row.kind,
    title: row.title || t("jobs.kind.task"),
    subtitle: row.subtitle,
    log_url: row.log_url,
    primary_route: row.primary_route,
  };
}
</script>

<template>
  <Teleport to="body">
    <aside
      :class="[
        'fixed top-[60px] z-30 flex w-[22rem] max-w-[92vw] flex-col transition-[right] duration-200 ease-out',
        props.copilotOpen ? 'max-xl:hidden xl:right-[26rem]' : 'right-3',
      ]"
      :aria-label="t('jobs.history_title')"
    >
      <div class="glass-panel glass-popover relative flex max-h-[min(34rem,calc(100vh-5rem))] flex-col rounded-[18px]">
        <header class="flex shrink-0 items-center gap-2 px-4 pb-2 pt-3">
          <History class="h-4 w-4 shrink-0 text-ink-muted" />
          <span class="text-callout font-semibold text-ink-primary">
            {{ t("jobs.history_title") }}
          </span>
          <span class="flex-1"></span>
          <button
            type="button"
            class="icon-btn !h-7 !w-7"
            :aria-label="t('jobs.collapse')"
            :title="t('jobs.collapse')"
            @click="$emit('close')"
          >
            <X class="h-3.5 w-3.5" />
          </button>
        </header>

        <div
          v-if="loadFailed"
          class="px-4 pb-4 text-footnote text-danger"
        >
          {{ t("jobs.history_failed") }}
        </div>
        <div
          v-else-if="!loading && rows.length === 0"
          class="px-4 pb-4 text-footnote text-ink-muted"
        >
          {{ t("jobs.history_empty") }}
        </div>

        <ul
          v-if="rows.length"
          class="min-h-0 space-y-0.5 overflow-y-auto overscroll-contain px-2 pb-2"
        >
          <li v-for="row in rows" :key="row.id">
            <button
              type="button"
              class="job-row focus-ring"
              :title="t('jobs.open_transcript')"
              @click="open(row)"
            >
              <span class="job-row-icon">
                <component :is="kindIcon(row.kind)" class="h-3.5 w-3.5" />
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5">
                  <div class="min-w-0 flex-1 truncate text-footnote font-semibold text-ink-primary">
                    {{ row.title || kindLabel(row.kind) }}
                  </div>
                  <span
                    class="chip shrink-0"
                    :class="
                      outcome(row) === 'done'
                        ? 'bg-success-soft text-success-ink'
                        : outcome(row) === 'cancelled'
                          ? 'bg-ink-primary/[0.06] text-ink-muted'
                          : 'bg-danger-soft text-danger-ink'
                    "
                  >
                    <CheckCircle2 v-if="outcome(row) === 'done'" class="h-3 w-3" />
                    <XCircle v-else class="h-3 w-3" />
                    {{ outcomeLabel(row) }}
                  </span>
                </div>
                <div class="truncate text-caption1 text-ink-muted">
                  <span>{{ kindLabel(row.kind) }}</span>
                  <span v-if="row.subtitle"> · {{ row.subtitle }}</span>
                </div>
                <div
                  class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-caption1 text-ink-subtle tabular"
                >
                  <span v-if="timingLine(row)">{{ timingLine(row) }}</span>
                  <span v-if="row.claude_cost_usd != null">
                    ${{ Number(row.claude_cost_usd).toFixed(2) }}
                  </span>
                  <span v-if="row.finished_at" class="ml-auto">
                    {{ t("jobs.age_ago", { age: fmtAge(row.finished_at) }) }}
                  </span>
                </div>
                <div
                  v-if="outcome(row) === 'failed' && row.error"
                  class="mt-1 line-clamp-2 text-caption1 text-danger"
                >
                  {{ row.error }}
                </div>
              </div>
            </button>
          </li>
        </ul>
      </div>
    </aside>

    <JobLogModal v-if="openJob" :job="openJob" @close="openJob = null" />
  </Teleport>
</template>
