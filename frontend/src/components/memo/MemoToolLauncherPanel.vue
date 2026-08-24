<script setup>
import { computed } from "vue";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ClipboardCheck,
  Gauge,
  Loader2,
  Play,
  ShieldAlert,
} from "lucide-vue-next";
import AiMark from "../AiMark.vue";
import MemoGraderPanel from "./MemoGraderPanel.vue";

const props = defineProps({
  tools: { type: Array, default: () => [] },
  runningTool: { type: String, default: null },
  savingArtifact: { type: String, default: null },
  memoGrader: { type: Object, default: null },
  completedMemoRuns: { type: Array, default: () => [] },
  toolPrompts: { type: Object, default: () => ({}) },
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
  return AiMark;
}

const visibleTools = computed(() =>
  props.tools.filter((tool) => tool?.visibility !== "hidden" && tool?.stage !== "hidden"),
);
const coreTools = computed(() =>
  visibleTools.value.filter((tool) => tool?.critical || tool?.stage === "core" || !tool?.stage),
);
const optionalTools = computed(() =>
  visibleTools.value.filter((tool) => !tool?.critical && tool?.stage === "optional"),
);
const afterMemoTools = computed(() =>
  visibleTools.value.filter((tool) => tool?.stage === "after_memo"),
);

function promptsFor(tool) {
  const rows = props.toolPrompts?.[tool?.name];
  return Array.isArray(rows) ? rows.slice(0, 4) : [];
}

function promptTitle(prompt, index) {
  if (typeof prompt === "string") return `Question ${index + 1}`;
  return prompt?.label || prompt?.title || `Question ${index + 1}`;
}

function promptText(prompt) {
  if (typeof prompt === "string") return prompt;
  return prompt?.text || prompt?.question || prompt?.prompt || prompt?.detail || "";
}

function preworkLabel(tool) {
  if (tool.status === "running") return "Pre-work running";
  if (tool.status === "done") return promptsFor(tool).length ? "Ready for user input" : "Pre-work complete";
  if (tool.status === "error") return "Pre-work error";
  return "Pre-work not run";
}

function preworkIcon(tool) {
  if (tool.status === "done") return CheckCircle2;
  if (tool.status === "error") return AlertTriangle;
  return Loader2;
}

function preworkClass(tool) {
  if (tool.status === "done") return "border-success/30 bg-success-soft text-success-ink";
  if (tool.status === "error") return "border-danger/30 bg-danger/10 text-danger";
  if (tool.status === "running") return "border-warning/40 bg-warning-soft text-warning-ink";
  return "border-subtle bg-surface-muted text-ink-muted";
}

function runLabel(tool) {
  if (tool.status === "done") return "Rerun";
  return tool.run_label || "Run";
}

function fmtDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
</script>

<template>
  <section class="space-y-3">
    <div class="flex items-center justify-between gap-3">
      <h3 class="font-display text-title3 text-ink-primary">
        Core Memo Workflow
      </h3>
    </div>
    <div class="grid gap-3">
      <article
        v-for="tool in coreTools"
        :key="tool.name"
        class="rounded-card bg-surface p-4"
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
                :class="[ 'text-[10px] px-1.5 py-0.5 rounded ', statusClass(tool.status), ]"
              >
                {{ tool.status.replace('_', ' ') }}
              </span>
            </div>
            <p class="mt-1 text-sm text-ink-secondary">
              {{ tool.description }}
            </p>
            <div
              :class="[ 'mt-3 inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[11px] font-medium ', preworkClass(tool), ]"
            >
              <component
                :is="preworkIcon(tool)"
                :class="[ 'h-3.5 w-3.5', tool.status === 'running' ? 'animate-spin' : '', ]"
              />
              <span>{{ preworkLabel(tool) }}</span>
            </div>
            <div
              v-if="tool.status === 'done' && tool.input_label"
              class="mt-2 text-xs font-medium text-ink-primary"
            >
              {{ tool.input_label }}
            </div>
            <div
              v-if="promptsFor(tool).length"
              class="mt-2 space-y-2"
            >
              <div
                v-for="(prompt, index) in promptsFor(tool)"
                :key="`${tool.name}-prompt-${index}`"
                class="rounded-subbox bg-fill-tertiary px-3 py-2"
              >
                <div class="text-[11px] font-medium text-footnote font-semibold text-ink-muted">
                  {{ promptTitle(prompt, index) }}
                </div>
                <div class="mt-1 text-sm text-ink-primary">
                  {{ promptText(prompt) }}
                </div>
              </div>
            </div>
            <div v-if="tool.summary" class="mt-2 text-xs text-ink-muted">
              {{ tool.summary }}
            </div>
            <div v-if="tool.last_run_at" class="mt-1 text-[11px] text-ink-subtle">
              {{ fmtDate(tool.last_run_at) }}
            </div>
          </div>
          <button
            type="button"
            @click="emit('run-tool', tool.name)"
            :disabled="Boolean(runningTool) || tool.status === 'running'"
            class="btn-bordered h-9 shrink-0 focus-ring"
            :title="`Run ${tool.label}`"
          >
            <Loader2
              v-if="runningTool === tool.name || tool.status === 'running'"
              class="h-4 w-4 animate-spin"
            />
            <Play v-else class="h-4 w-4" />
            <span>{{ runLabel(tool) }}</span>
          </button>
        </div>
      </article>
    </div>

    <details
      v-if="optionalTools.length"
      class="rounded-card bg-surface p-4"
    >
      <summary class="cursor-pointer text-sm font-medium text-ink-primary focus-ring">
        Optional Memo Tools
      </summary>
      <div class="mt-3 divide-y divide-subtle/70">
        <div
          v-for="tool in optionalTools"
          :key="tool.name"
          class="py-3 first:pt-0 last:pb-0"
        >
          <div class="flex items-start gap-3">
            <component
              :is="toolIcon(tool.name)"
              class="mt-0.5 h-4 w-4 shrink-0 text-accent"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 flex-wrap">
                <div class="font-medium text-ink-primary">{{ tool.label }}</div>
                <span
                  :class="[ 'text-[10px] px-1.5 py-0.5 rounded ', statusClass(tool.status), ]"
                >
                  {{ tool.status.replace('_', ' ') }}
                </span>
              </div>
              <p class="mt-1 text-sm text-ink-secondary">
                {{ tool.description }}
              </p>
              <div
                v-if="tool.status === 'done' && tool.input_label"
                class="mt-2 text-xs font-medium text-ink-primary"
              >
                {{ tool.input_label }}
              </div>
              <div
                v-if="promptsFor(tool).length"
                class="mt-2 space-y-2"
              >
                <div
                  v-for="(prompt, index) in promptsFor(tool)"
                  :key="`${tool.name}-optional-prompt-${index}`"
                  class="rounded-subbox bg-fill-tertiary px-3 py-2"
                >
                  <div class="text-[11px] font-medium text-footnote font-semibold text-ink-muted">
                    {{ promptTitle(prompt, index) }}
                  </div>
                  <div class="mt-1 text-sm text-ink-primary">
                    {{ promptText(prompt) }}
                  </div>
                </div>
              </div>
              <div v-if="tool.summary" class="mt-2 text-xs text-ink-muted">
                {{ tool.summary }}
              </div>
              <div v-if="tool.last_run_at" class="mt-1 text-[11px] text-ink-subtle">
                {{ fmtDate(tool.last_run_at) }}
              </div>
            </div>
            <button
              type="button"
              @click="emit('run-tool', tool.name)"
              :disabled="Boolean(runningTool) || tool.status === 'running'"
              class="btn-bordered btn-sm h-8 shrink-0 focus-ring"
              :title="`Run ${tool.label}`"
            >
              <Loader2
                v-if="runningTool === tool.name || tool.status === 'running'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Play v-else class="h-3.5 w-3.5" />
              <span>{{ runLabel(tool) }}</span>
            </button>
          </div>
        </div>
      </div>
    </details>

    <details
      v-if="afterMemoTools.length"
      class="rounded-card bg-surface p-4"
    >
      <summary class="cursor-pointer text-sm font-medium text-ink-primary focus-ring">
        After Memo
      </summary>
      <div class="mt-3 divide-y divide-subtle/70">
        <div
          v-for="tool in afterMemoTools"
          :key="tool.name"
          class="py-3 first:pt-0 last:pb-0"
        >
          <div class="flex items-start gap-3">
            <component
              :is="toolIcon(tool.name)"
              class="mt-0.5 h-4 w-4 shrink-0 text-accent"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 flex-wrap">
                <div class="font-medium text-ink-primary">{{ tool.label }}</div>
                <span
                  :class="[ 'text-[10px] px-1.5 py-0.5 rounded ', statusClass(tool.status), ]"
                >
                  {{ tool.status.replace('_', ' ') }}
                </span>
              </div>
              <p class="mt-1 text-sm text-ink-secondary">
                {{ tool.description }}
              </p>
              <MemoGraderPanel
                v-if="tool.name === 'memo_grader'"
                :memo-grader="memoGrader"
                :completed-memo-runs="completedMemoRuns"
                :saving-artifact="savingArtifact"
                @select-memo-for-grading="emit('select-memo-for-grading', $event)"
              />
              <div v-if="tool.summary" class="mt-2 text-xs text-ink-muted">
                {{ tool.summary }}
              </div>
              <div v-if="tool.last_run_at" class="mt-1 text-[11px] text-ink-subtle">
                {{ fmtDate(tool.last_run_at) }}
              </div>
            </div>
            <button
              type="button"
              @click="emit('run-tool', tool.name)"
              :disabled="Boolean(runningTool) || tool.status === 'running'"
              class="btn-bordered btn-sm h-8 shrink-0 focus-ring"
              :title="`Run ${tool.label}`"
            >
              <Loader2
                v-if="runningTool === tool.name || tool.status === 'running'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Play v-else class="h-3.5 w-3.5" />
              <span>{{ runLabel(tool) }}</span>
            </button>
          </div>
        </div>
      </div>
    </details>
  </section>
</template>
