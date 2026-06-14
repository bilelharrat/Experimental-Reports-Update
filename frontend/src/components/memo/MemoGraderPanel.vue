<script setup>
defineProps({
  memoGrader: { type: Object, default: null },
  completedMemoRuns: { type: Array, default: () => [] },
  savingArtifact: { type: String, default: null },
});

const emit = defineEmits(["select-memo-for-grading"]);
</script>

<template>
  <div class="mt-3 space-y-2">
    <select
      :value="memoGrader?.selected_report_id || memoGrader?.completed_report_id || ''"
      @change="emit('select-memo-for-grading', $event.target.value)"
      :disabled="Boolean(savingArtifact) || completedMemoRuns.length === 0"
      class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-xs text-ink-primary focus-ring"
    >
      <option value="">
        {{ completedMemoRuns.length ? "Select completed memo" : "No completed memos" }}
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
      class="rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-xs text-ink-secondary"
    >
      <div class="font-medium text-ink-primary">
        Graded {{ memoGrader.completed_report_id }}
      </div>
      <div v-if="memoGrader.confidence" class="mt-1 text-ink-muted">
        Confidence: {{ memoGrader.confidence }}
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
