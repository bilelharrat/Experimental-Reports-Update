<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Loader2, Sparkles, X } from "lucide-vue-next";
import { api } from "../api.js";
import { openSummary } from "../state.js";

const jobs = ref([]);
const collapsed = ref(false);
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
  if (!j.slide_count || !j.slide_no) return null;
  return Math.round((j.slide_no / j.slide_count) * 100);
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

async function open(j) {
  // Need the file record to pass to the modal — fetch the company's file list
  // and pick the matching one. (Cheap; this isn't a hot path.)
  let file;
  try {
    const list = await api.listFiles(j.company_id);
    file = list.find((f) => f.id === j.file_id);
  } catch {
    file = { id: j.file_id, filename: j.filename, kind: j.kind };
  }
  openSummary(j.company_id, file || { id: j.file_id, filename: j.filename, kind: j.kind });
}

const visible = computed(() => jobs.value.length > 0);
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="visible"
      class="fixed top-4 right-4 z-40 w-72 max-w-[88vw] flex flex-col gap-2"
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
          Active jobs · {{ jobs.length }}
        </span>
        <span class="flex-1"></span>
        <button
          type="button"
          @click="collapsed = !collapsed"
          class="text-ink-muted hover:text-ink-primary text-xs focus-ring rounded"
          :title="collapsed ? 'Expand' : 'Collapse'"
        >
          {{ collapsed ? "▾" : "▴" }}
        </button>
      </header>

      <ul v-if="!collapsed" class="space-y-2">
        <li
          v-for="j in jobs"
          :key="`${j.company_id}/${j.file_id}`"
          class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
        >
          <button
            type="button"
            @click="open(j)"
            class="w-full text-left p-3 hover:bg-surface-muted focus-ring"
          >
            <div class="flex items-start gap-2">
              <Sparkles class="h-3.5 w-3.5 text-accent mt-0.5 shrink-0" />
              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium text-ink-primary truncate">
                  {{ j.label || j.filename }}
                </div>
                <div class="text-xs text-ink-muted truncate">
                  {{ j.company_id }}
                  <span v-if="j.speed" class="ml-1 px-1 rounded bg-surface-muted font-mono uppercase text-[10px]">
                    {{ j.speed }}
                  </span>
                </div>
                <div
                  v-if="j.latest_stage"
                  class="mt-1 text-xs text-ink-secondary line-clamp-2 inline-flex items-center gap-1"
                >
                  <Loader2 class="h-3 w-3 animate-spin shrink-0 text-accent" />
                  <span>{{ j.latest_stage }}</span>
                </div>
                <div
                  v-if="j.slide_no && j.slide_count"
                  class="mt-1.5 h-1 w-full rounded-full bg-surface-muted overflow-hidden"
                >
                  <div
                    class="h-full bg-accent transition-all"
                    :style="{ width: pct(j) + '%' }"
                  ></div>
                </div>
                <div class="mt-1 flex items-center gap-2 text-[10px] text-ink-muted font-mono">
                  <span v-if="j.slide_no && j.slide_count">
                    {{ j.slide_no }}/{{ j.slide_count }}
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
  </Teleport>
</template>
