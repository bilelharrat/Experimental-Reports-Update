<script setup>
import {
  BarChart3,
  ClipboardCheck,
  Gauge,
  Loader2,
  Play,
  ShieldAlert,
  Sparkles,
} from "lucide-vue-next";
import MemoGraderPanel from "./MemoGraderPanel.vue";

defineProps({
  tools: { type: Array, default: () => [] },
  runningTool: { type: String, default: null },
  savingArtifact: { type: String, default: null },
  memoGrader: { type: Object, default: null },
  completedMemoRuns: { type: Array, default: () => [] },
});

const emit = defineEmits(["run-tool", "select-memo-for-grading"]);

function statusClass(status) {
  if (status === "done" || status === "supported") return "bg-success-soft text-success-ink";
  if (status === "error" || status === "contradicted") return "bg-danger/10 text-danger";
  if (status === "mixed" || status === "partial") return "bg-warning-soft text-warning-ink";
  if (status === "missing" || status === "not_started") return "bg-surface-muted text-ink-muted";
  return "bg-warning-soft text-warning-ink";
}

function toolIcon(name) {
  if (name.includes("risk")) return ShieldAlert;
  if (name.includes("chart") || name.includes("benchmark")) return BarChart3;
  if (name.includes("readiness")) return Gauge;
  if (name.includes("grader")) return ClipboardCheck;
  return Sparkles;
}

function fmtDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
</script>

<template>
  <section>
    <div class="mb-3 flex items-center justify-between">
      <h3 class="font-display text-lg font-semibold text-ink-primary">
        Tools
      </h3>
    </div>
    <div class="grid lg:grid-cols-2 gap-3">
      <div
        v-for="tool in tools"
        :key="tool.name"
        class="rounded-card border border-subtle bg-surface p-4"
      >
        <div class="flex items-start gap-3">
          <component
            :is="toolIcon(tool.name)"
            class="h-5 w-5 text-accent mt-0.5 shrink-0"
          />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <div class="font-medium text-ink-primary">{{ tool.label }}</div>
              <span
                :class="[
                  'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                  statusClass(tool.status),
                ]"
              >
                {{ tool.status.replace('_', ' ') }}
              </span>
            </div>
            <p class="mt-1 text-sm text-ink-secondary">
              {{ tool.description }}
            </p>
            <div v-if="tool.summary" class="mt-2 text-xs text-ink-muted">
              {{ tool.summary }}
            </div>
            <MemoGraderPanel
              v-if="tool.name === 'memo_grader'"
              :memo-grader="memoGrader"
              :completed-memo-runs="completedMemoRuns"
              :saving-artifact="savingArtifact"
              @select-memo-for-grading="emit('select-memo-for-grading', $event)"
            />
            <div v-if="tool.last_run_at" class="mt-1 text-[11px] text-ink-subtle">
              {{ fmtDate(tool.last_run_at) }}
            </div>
          </div>
          <button
            type="button"
            @click="emit('run-tool', tool.name)"
            :disabled="Boolean(runningTool) || tool.status === 'running'"
            class="h-9 w-9 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring"
            :title="`Run ${tool.label}`"
          >
            <Loader2
              v-if="runningTool === tool.name || tool.status === 'running'"
              class="h-4 w-4 animate-spin"
            />
            <Play v-else class="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
