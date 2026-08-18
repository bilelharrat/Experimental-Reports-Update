<script setup>
import { AlertTriangle, Loader2, Play } from "lucide-vue-next";

defineProps({
  tasks: { type: Array, default: () => [] },
  sourceFiles: { type: Array, default: () => [] },
  batchStatus: { type: Object, default: null },
  runningBatch: { type: Boolean, default: false },
  hasRunningTasks: { type: Boolean, default: false },
  runningTask: { type: String, default: null },
  cancellingTask: { type: String, default: null },
  savingTask: { type: String, default: null },
});

const emit = defineEmits([
  "run-selected-tasks",
  "run-research-task",
  "cancel-research-task",
  "toggle-task-source",
]);

function statusClass(status) {
  if (status === "done" || status === "supported") return "bg-success-soft text-success-ink";
  if (status === "error" || status === "contradicted") return "bg-danger/10 text-danger";
  if (status === "mixed" || status === "partial") return "bg-warning-soft text-warning-ink";
  if (status === "missing" || status === "not_started") return "bg-surface-muted text-ink-muted";
  return "bg-warning-soft text-warning-ink";
}

function statusLabel(status) {
  return (status || "not_started").replaceAll("_", " ");
}

function listItems(value) {
  return Array.isArray(value) ? value : [];
}

function sourceLabel(source) {
  if (typeof source === "string") return source;
  return source?.filename || source?.id || "Source";
}

function evidenceLabel(item) {
  const locator = item?.locator || item?.filename || item?.file_id;
  return locator || "Source trace";
}

function sourceCheckedText(task) {
  return listItems(task?.sources_checked).map(sourceLabel).join(", ");
}

function taskSourceIds(task) {
  return Array.isArray(task?.selected_source_ids) ? task.selected_source_ids : [];
}

function isSourceSelected(task, sourceId) {
  return taskSourceIds(task).includes(sourceId);
}

function fmtDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
</script>

<template>
  <div class="border border-subtle bg-surface rounded-card p-5">
    <div class="flex items-center justify-between gap-3">
      <h3 class="font-display text-title3 text-ink-primary">
        Research Task Queue
      </h3>
      <button
        v-if="tasks.length"
        type="button"
        @click="emit('run-selected-tasks')"
        :disabled="runningBatch || hasRunningTasks"
        class="btn-bordered btn-sm focus-ring"
      >
        <Loader2 v-if="runningBatch" class="h-3.5 w-3.5 animate-spin" />
        <Play v-else class="h-3.5 w-3.5" />
        <span>Run selected</span>
      </button>
    </div>
    <div
      v-if="batchStatus"
      class="mt-3 rounded-subbox bg-fill-tertiary px-3 py-2 text-xs text-ink-secondary"
    >
      <div>
        Launched {{ batchStatus.launched_task_ids?.length || 0 }} tasks · concurrency {{ batchStatus.concurrency }}
      </div>
      <div class="mt-1 text-ink-muted">
        <span
          v-for="(status, taskId) in batchStatus.statuses"
          :key="taskId"
          class="mr-2"
        >
          {{ taskId }}: {{ status.replaceAll('_', ' ') }}
        </span>
      </div>
    </div>
    <div v-if="tasks.length === 0" class="mt-3 text-sm text-ink-muted">
      No research tasks yet.
    </div>
    <div v-else class="mt-3 space-y-2">
      <div
        v-for="task in tasks"
        :key="task.id"
        :id="`memo-task-${task.id}`"
        class="rounded-subbox bg-fill-tertiary p-3"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <div class="text-sm font-medium text-ink-primary">{{ task.title }}</div>
              <span class="text-[10px] rounded bg-surface px-1.5 py-0.5 text-ink-muted uppercase">
                {{ task.priority }}
              </span>
              <span
                :class="[ 'text-[10px] px-1.5 py-0.5 rounded ', statusClass(task.status), ]"
              >
                {{ statusLabel(task.status) }}
              </span>
            </div>
            <div class="mt-1 text-xs text-ink-muted">{{ task.source_type }}</div>
            <div class="mt-2 text-xs text-ink-secondary">{{ task.prompt }}</div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button
              type="button"
              @click="emit('run-research-task', task.id)"
              :disabled="Boolean(runningTask) || task.status === 'running'"
              class="btn-bordered btn-sm h-8 w-8 focus-ring"
              :title="task.status === 'running' ? 'Task running' : task.status === 'done' ? 'Run task again' : 'Run task'"
            >
              <Loader2
                v-if="runningTask === task.id || task.status === 'running'"
                class="h-4 w-4 animate-spin"
              />
              <Play v-else class="h-4 w-4" />
            </button>
            <button
              v-if="task.status === 'running'"
              type="button"
              @click="emit('cancel-research-task', task.id)"
              :disabled="cancellingTask === task.id"
              class="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-danger/30 bg-danger/10 text-danger hover:bg-danger/15 disabled:opacity-60 focus-ring"
              title="Cancel task"
            >
              <Loader2
                v-if="cancellingTask === task.id"
                class="h-4 w-4 animate-spin"
              />
              <AlertTriangle v-else class="h-4 w-4" />
            </button>
          </div>
        </div>
        <div
          v-if="sourceFiles.length"
          class="mt-3 rounded-card bg-surface shadow-card px-3 py-2"
        >
          <div class="text-[11px] text-footnote font-semibold text-ink-muted">
            Sources
          </div>
          <div class="mt-2 flex flex-wrap gap-2">
            <label
              v-for="source in sourceFiles"
              :key="source.id"
              class="inline-flex items-center gap-1.5 rounded border border-subtle bg-surface-muted px-2 py-1 text-xs text-ink-secondary"
            >
              <input
                type="checkbox"
                :checked="isSourceSelected(task, source.id)"
                :disabled="savingTask === task.id || task.status === 'running'"
                @change="emit('toggle-task-source', task, source.id, $event.target.checked)"
                class="h-3.5 w-3.5 rounded border-subtle text-accent focus-ring"
              />
              <span>{{ sourceLabel(source) }}</span>
            </label>
          </div>
          <div
            v-if="taskSourceIds(task).length === 0"
            class="mt-2 text-[11px] text-ink-muted"
          >
            All research-folder sources will be available.
          </div>
        </div>
        <div
          v-if="task.result_summary || task.answer"
          class="mt-3 rounded-card bg-surface shadow-card px-3 py-2 text-xs text-ink-secondary"
        >
          <div class="font-medium text-ink-primary">
            {{ task.answer || task.result_summary }}
          </div>
          <div
            v-if="task.confidence || task.sources_checked?.length"
            class="mt-1 text-[11px] text-ink-muted"
          >
            <span v-if="task.confidence">Confidence: {{ task.confidence }}</span>
            <span v-if="task.sources_checked?.length">
              · Sources checked: {{ sourceCheckedText(task) }}
            </span>
          </div>
          <div
            v-if="listItems(task.supporting_evidence).length"
            class="mt-3"
          >
            <div class="text-[11px] text-success-ink">
              Supporting evidence
            </div>
            <div
              v-for="(item, index) in listItems(task.supporting_evidence)"
              :key="`support-${task.id}-${index}`"
              class="mt-1 rounded border border-subtle bg-surface-muted px-2 py-1"
            >
              <div class="text-[11px] text-ink-muted">{{ evidenceLabel(item) }}</div>
              <div>{{ item.excerpt }}</div>
            </div>
          </div>
          <div
            v-if="listItems(task.contradicting_evidence).length"
            class="mt-3"
          >
            <div class="text-[11px] text-danger">
              Contradicting evidence
            </div>
            <div
              v-for="(item, index) in listItems(task.contradicting_evidence)"
              :key="`contradict-${task.id}-${index}`"
              class="mt-1 rounded border border-subtle bg-surface-muted px-2 py-1"
            >
              <div class="text-[11px] text-ink-muted">{{ evidenceLabel(item) }}</div>
              <div>{{ item.excerpt }}</div>
            </div>
          </div>
          <div
            v-if="listItems(task.open_questions).length"
            class="mt-3"
          >
            <div class="text-[11px] text-warning-ink">
              Evidence limits
            </div>
            <ul class="mt-1 space-y-1">
              <li
                v-for="(question, index) in listItems(task.open_questions)"
                :key="`question-${task.id}-${index}`"
              >
                {{ question }}
              </li>
            </ul>
          </div>
          <div
            v-if="task.completed_at || task.last_run_at"
            class="mt-1 text-[11px] text-ink-subtle"
          >
            {{ fmtDate(task.completed_at || task.last_run_at) }}
            <span v-if="task.result_generated_by">
              · {{ task.result_generated_by.replaceAll('_', ' ') }}
            </span>
          </div>
        </div>
        <div v-if="task.error" class="mt-2 text-xs text-danger">
          {{ task.error }}
        </div>
      </div>
    </div>
  </div>
</template>
