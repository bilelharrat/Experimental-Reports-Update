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
        'fixed top-14 z-30 w-80 max-w-[88vw] flex flex-col gap-2 transition-[right] duration-200 ease-out',
        props.copilotOpen ? 'max-xl:hidden xl:right-[26rem]' : 'right-4',
      ]"
    >
      <header
        class="flex items-center gap-2 px-3 py-2 rounded-card border border-subtle bg-surface shadow-card"
      >
        <History class="h-4 w-4 shrink-0 text-ink-muted" />
        <span class="vogue-label text-ink-secondary">
          {{ t("jobs.history_title") }}
        </span>
        <span class="flex-1"></span>
        <button
          type="button"
          class="text-ink-muted hover:text-ink-primary focus-ring rounded"
          :aria-label="t('jobs.collapse')"
          @click="$emit('close')"
        >
          <X class="h-3.5 w-3.5" />
        </button>
      </header>

      <div
        v-if="loadFailed"
        class="rounded-card border border-subtle bg-surface px-3 py-3 text-xs text-danger shadow-card"
      >
        {{ t("jobs.history_failed") }}
      </div>
      <div
        v-else-if="!loading && rows.length === 0"
        class="rounded-card border border-subtle bg-surface px-3 py-3 text-xs text-ink-muted shadow-card"
      >
        {{ t("jobs.history_empty") }}
      </div>

      <ul
        v-if="rows.length"
        class="max-h-[min(30rem,calc(100vh-7.5rem))] space-y-2 overflow-y-auto overscroll-contain pr-0.5"
      >
        <li
          v-for="row in rows"
          :key="row.id"
          class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
        >
          <button
            type="button"
            class="w-full text-left p-3 hover:bg-surface-muted focus-ring"
            :title="t('jobs.open_transcript')"
            @click="open(row)"
          >
            <div class="flex items-start gap-2">
              <component
                :is="kindIcon(row.kind)"
                class="h-3.5 w-3.5 text-ink-muted mt-0.5 shrink-0"
              />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5">
                  <div class="text-sm font-medium text-ink-primary truncate flex-1">
                    {{ row.title || kindLabel(row.kind) }}
                  </div>
                  <span
                    class="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase shrink-0"
                    :class="
                      outcome(row) === 'done'
                        ? 'bg-success-soft text-success-ink'
                        : outcome(row) === 'cancelled'
                          ? 'bg-fill-tertiary text-ink-muted'
                          : 'bg-danger/10 text-danger'
                    "
                  >
                    <CheckCircle2
                      v-if="outcome(row) === 'done'"
                      class="h-3 w-3"
                    />
                    <XCircle v-else class="h-3 w-3" />
                    {{ outcomeLabel(row) }}
                  </span>
                </div>
                <div class="text-xs text-ink-muted truncate">
                  <span class="font-mono uppercase text-[10px]">{{
                    kindLabel(row.kind)
                  }}</span>
                  <span v-if="row.subtitle"> · {{ row.subtitle }}</span>
                </div>
                <div
                  class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-ink-muted font-mono"
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
                  class="mt-1 text-[11px] text-danger line-clamp-2"
                >
                  {{ row.error }}
                </div>
              </div>
            </div>
          </button>
        </li>
      </ul>
    </aside>

    <JobLogModal v-if="openJob" :job="openJob" @close="openJob = null" />
  </Teleport>
</template>
