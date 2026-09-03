<script setup>
import { computed } from "vue";
import { useT } from "../../i18n.js";

const props = defineProps({
  memoGrader: { type: Object, default: null },
  completedMemoRuns: { type: Array, default: () => [] },
  savingArtifact: { type: String, default: null },
});

const emit = defineEmits(["select-memo-for-grading"]);
const t = useT();

const scoreRows = computed(() => {
  const scores = props.memoGrader?.scores;
  if (!Array.isArray(scores)) return [];
  return scores.filter((row) => row && typeof row === "object" && row.area);
});

const strongestSections = computed(() => {
  const rows = props.memoGrader?.strongest_sections;
  return Array.isArray(rows) ? rows.filter(Boolean) : [];
});

const weakestSections = computed(() => {
  const rows = props.memoGrader?.weakest_sections;
  return Array.isArray(rows) ? rows.filter(Boolean) : [];
});
</script>

<template>
  <div class="mt-3 space-y-2">
    <select
      :value="memoGrader?.selected_report_id || memoGrader?.completed_report_id || ''"
      @change="emit('select-memo-for-grading', $event.target.value)"
      :disabled="Boolean(savingArtifact) || completedMemoRuns.length === 0"
      class="field field-sm focus-ring"
    >
      <option value="">
        {{ completedMemoRuns.length ? t("memo.grader_select") : t("memo.grader_none") }}
      </option>
      <option
        v-for="run in completedMemoRuns"
        :key="run.id"
        :value="run.id"
      >
        {{ run.run_id || run.id }}
      </option>
    </select>
    <div
      v-if="memoGrader?.status === 'graded'"
      class="rounded-subbox bg-fill-tertiary px-3 py-2 text-xs text-ink-secondary"
    >
      <div class="font-medium text-ink-primary">
        {{ t("memo.grader_graded") }} {{ memoGrader.completed_report_id }}
      </div>
      <div v-if="memoGrader.confidence" class="mt-1 text-ink-muted">
        {{ t("memo.grader_confidence") }}: {{ memoGrader.confidence }}
      </div>
      <ul v-if="scoreRows.length" class="mt-2 space-y-1">
        <li
          v-for="row in scoreRows"
          :key="row.area"
          class="flex items-baseline justify-between gap-3"
        >
          <span class="min-w-0 truncate text-ink-secondary">{{ row.area }}</span>
          <span class="mono-data shrink-0 font-semibold text-ink-primary">{{ row.score }}</span>
        </li>
      </ul>
      <div v-if="strongestSections.length" class="mt-2">
        <div class="font-medium text-ink-primary">{{ t("memo.grader_strongest") }}</div>
        <ul class="mt-1 space-y-0.5 text-ink-muted">
          <li v-for="section in strongestSections.slice(0, 4)" :key="`strong-${section}`">
            {{ section }}
          </li>
        </ul>
      </div>
      <div v-if="weakestSections.length" class="mt-2">
        <div class="font-medium text-ink-primary">{{ t("memo.grader_weakest") }}</div>
        <ul class="mt-1 space-y-0.5 text-ink-muted">
          <li v-for="section in weakestSections.slice(0, 4)" :key="`weak-${section}`">
            {{ section }}
          </li>
        </ul>
      </div>
      <ul v-if="memoGrader.lessons_for_future_memo_runs?.length" class="mt-2 space-y-1">
        <li
          v-for="lesson in memoGrader.lessons_for_future_memo_runs.slice(0, 3)"
          :key="lesson"
        >
          {{ lesson }}
        </li>
      </ul>
    </div>
  </div>
</template>
