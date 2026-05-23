<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  Brain,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Globe,
  Languages,
  Loader2,
  MousePointerClick,
  Pencil,
  Search,
  Sparkles,
  Terminal,
} from "lucide-vue-next";
import { api } from "../api.js";
import JobLogModal from "./JobLogModal.vue";

const jobs = ref([]);
const collapsed = ref(false);
const openJob = ref(null);
let pollId = null;

async function tick() {
  try {
    jobs.value = await api.listActiveJobs();
  } catch {
    // network blip — keep prior value
  }
}

onMounted(() => {
  tick();
  pollId = setInterval(tick, 3000);
});
onBeforeUnmount(() => {
  if (pollId) clearInterval(pollId);
});

function pct(j) {
  if (j.kind === "summary" && j.slide_count && j.slide_no) {
    return Math.round((j.slide_no / j.slide_count) * 100);
  }
  if (j.kind === "pdf_translation" && j.page_count && j.page_no) {
    return Math.round((j.page_no / j.page_count) * 100);
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
  return null;
}

function fmtAge(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

function kindIcon(kind) {
  if (kind === "search") return Search;
  if (kind === "pdf_translation") return Languages;
  if (kind === "summary") return FileText;
  if (kind === "external_research") return FileText;
  if (kind === "research_summary") return Sparkles;
  if (kind === "memo") return Sparkles;
  return Sparkles;
}

function kindLabel(kind) {
  if (kind === "search") return "search";
  if (kind === "pdf_translation") return "translation";
  if (kind === "summary") return "deck summary";
  if (kind === "external_research") return "research analysis";
  if (kind === "research_summary") return "file summary";
  if (kind === "memo") return "memo";
  if (kind === "public_snapshot") return "trader snapshot";
  if (kind?.startsWith("console_")) return "console";
  return kind || "task";
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
    const t = (a.text || "").replace(/\s+/g, " ").trim();
    return trim(t, 200) || "Thinking…";
  }
  if (a.action === "tool_use") {
    const preview = (a.preview || "").replace(/\s+/g, " ").trim();
    return `${a.tool}: ${trim(preview, 160)}`;
  }
  if (a.action === "tool_result") {
    return `${a.tool} → ${a.is_error ? "error" : "ok"}`;
  }
  if (a.action === "init") return "Claude initialized";
  if (a.action === "result") return "Run finished";
  return null;
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
          AI tasks · {{ jobs.length }}
        </span>
        <span class="flex-1"></span>
        <button
          type="button"
          @click="collapsed = !collapsed"
          class="text-ink-muted hover:text-ink-primary text-xs focus-ring rounded inline-flex items-center"
          :title="collapsed ? 'Expand' : 'Collapse'"
        >
          <ChevronRight v-if="collapsed" class="h-3.5 w-3.5" />
          <ChevronDown v-else class="h-3.5 w-3.5" />
        </button>
      </header>

      <ul v-if="!collapsed" class="space-y-2">
        <li
          v-for="j in jobs"
          :key="`${j.kind}:${j.job_id || j.file_id || j.item_id || j.title}`"
          class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
        >
          <button
            type="button"
            @click="open(j)"
            class="w-full text-left p-3 hover:bg-surface-muted focus-ring group"
            :title="'Click to open the live transcript'"
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
                    {{ j.tool_count }} tool call{{ j.tool_count === 1 ? "" : "s" }}
                  </span>
                  <span v-if="j.claude_cost_usd != null">
                    ${{ Number(j.claude_cost_usd).toFixed(4) }}
                  </span>
                  <span v-if="j.last_event_at" class="ml-auto">
                    {{ fmtAge(j.last_event_at) }} ago
                  </span>
                </div>
              </div>
            </div>
          </button>
        </li>
      </ul>
    </aside>

    <JobLogModal v-if="openJob" :job="openJob" @close="close" />
  </Teleport>
</template>
