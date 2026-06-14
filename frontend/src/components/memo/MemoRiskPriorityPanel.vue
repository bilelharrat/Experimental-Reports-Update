<script setup>
import { ArrowDown, ArrowUp, Loader2, Save } from "lucide-vue-next";

defineProps({
  risks: { type: Array, default: () => [] },
  prioritizedRisks: { type: Array, default: () => [] },
  riskPriorityMap: { type: [Object, Map], default: () => new Map() },
  riskPriorityDraft: { type: Array, default: () => [] },
  savingArtifact: { type: String, default: null },
  canMoveRisk: { type: Function, default: () => false },
});

const emit = defineEmits([
  "save-risk-priorities",
  "move-risk-priority",
  "set-risk-selected",
]);
</script>

<template>
  <div class="border border-subtle bg-surface rounded-card p-5">
    <div class="flex items-center justify-between gap-3">
      <h3 class="font-display text-lg font-semibold text-ink-primary">
        Strategic Risk Board
      </h3>
      <button
        v-if="riskPriorityDraft.length"
        type="button"
        @click="emit('save-risk-priorities')"
        :disabled="Boolean(savingArtifact)"
        class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
      >
        <Loader2
          v-if="savingArtifact === 'risk_priorities'"
          class="h-3.5 w-3.5 animate-spin"
        />
        <Save v-else class="h-3.5 w-3.5" />
        <span>Save priorities</span>
      </button>
    </div>
    <div v-if="risks.length === 0" class="mt-3 text-sm text-ink-muted">
      No risks generated yet.
    </div>
    <div v-else class="mt-3 space-y-3">
      <div
        v-for="risk in prioritizedRisks"
        :key="risk.id"
        class="rounded-lg border border-subtle bg-surface-muted p-3"
      >
        <div class="flex items-start gap-3">
          <div class="flex w-8 shrink-0 flex-col items-center gap-1">
            <button
              type="button"
              @click="emit('move-risk-priority', risk.id, -1)"
              :disabled="!canMoveRisk(risk.id, -1) || Boolean(savingArtifact)"
              class="h-7 w-7 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface text-ink-muted hover:text-ink-primary hover:bg-surface-muted disabled:opacity-35 disabled:cursor-not-allowed focus-ring"
              title="Move risk up"
            >
              <ArrowUp class="h-3.5 w-3.5" />
            </button>
            <div class="text-[11px] font-mono text-ink-muted">
              #{{ riskPriorityMap.get(risk.id)?.rank || "—" }}
            </div>
            <button
              type="button"
              @click="emit('move-risk-priority', risk.id, 1)"
              :disabled="!canMoveRisk(risk.id, 1) || Boolean(savingArtifact)"
              class="h-7 w-7 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface text-ink-muted hover:text-ink-primary hover:bg-surface-muted disabled:opacity-35 disabled:cursor-not-allowed focus-ring"
              title="Move risk down"
            >
              <ArrowDown class="h-3.5 w-3.5" />
            </button>
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-start justify-between gap-3">
              <div class="font-medium text-ink-primary">{{ risk.title }}</div>
              <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                {{ risk.status }}
              </span>
            </div>
            <div class="mt-1 text-sm text-ink-secondary">
              {{ risk.decision_question }}
            </div>
            <div class="mt-2 text-xs text-ink-muted">
              {{ risk.why_it_matters }}
            </div>
          </div>
          <label class="shrink-0 inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
            <input
              type="checkbox"
              :checked="Boolean(riskPriorityMap.get(risk.id)?.selected)"
              @change="emit('set-risk-selected', risk.id, $event.target.checked)"
              :disabled="Boolean(savingArtifact)"
              class="h-3.5 w-3.5 rounded border-subtle text-accent focus-ring"
            />
            <span>Research</span>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>
