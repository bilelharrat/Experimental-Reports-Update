<script setup>
import { AlertTriangle, CheckCircle2, Save } from "lucide-vue-next";

defineProps({
  readiness: { type: Object, default: () => ({ score: 0, total: 0, gates: [] }) },
  readinessPct: { type: Number, default: 0 },
  readinessBlockers: { type: Array, default: () => [] },
  additionalAreas: { type: Array, default: () => [] },
  readinessReviewDraft: { type: Object, default: () => ({}) },
  savingArtifact: { type: String, default: null },
});

const emit = defineEmits([
  "update-readiness-review-draft",
  "save-readiness-review",
]);

function severityClass(severity) {
  if (severity === "high") return "bg-danger/10 text-danger border-danger/30";
  return "bg-warning-soft text-warning-ink border-warning/40";
}

function fmtDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
</script>

<template>
  <div class="space-y-6">
    <section class="border border-subtle bg-surface rounded-card p-5">
      <div class="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div class="text-xs uppercase tracking-wide text-ink-muted">
            Readiness
          </div>
          <div class="mt-1 text-2xl font-semibold text-ink-primary">
            {{ readiness.score }} / {{ readiness.total }}
          </div>
        </div>
        <div class="w-full sm:w-64">
          <div class="h-2 rounded-full bg-surface-muted overflow-hidden">
            <div
              class="h-full bg-accent transition-all"
              :style="{ width: readinessPct + '%' }"
            ></div>
          </div>
          <div class="mt-1 text-xs text-ink-muted text-right">
            {{ readinessPct }}%
          </div>
        </div>
      </div>
      <div class="mt-4 grid md:grid-cols-3 gap-2">
        <div
          v-for="gate in readiness.gates"
          :key="gate.id"
          class="flex items-center gap-2 rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-sm"
        >
          <CheckCircle2
            v-if="gate.status === 'done'"
            class="h-4 w-4 text-success shrink-0"
          />
          <AlertTriangle
            v-else
            class="h-4 w-4 text-warning-ink shrink-0"
          />
          <span class="text-ink-primary">{{ gate.label }}</span>
        </div>
      </div>
      <div
        v-if="readinessBlockers.length"
        class="mt-4 rounded-lg border border-warning/40 bg-warning-soft/60 p-3"
      >
        <div class="text-xs uppercase tracking-wide text-warning-ink">
          Approval blockers
        </div>
        <ul class="mt-2 space-y-1 text-sm text-warning-ink">
          <li v-for="blocker in readinessBlockers" :key="`${blocker.kind}-${blocker.id}`">
            {{ blocker.label }}
          </li>
        </ul>
      </div>
    </section>

    <section
      v-if="additionalAreas.length"
      class="border border-subtle bg-surface rounded-card p-5"
    >
      <h3 class="font-display text-lg font-semibold text-ink-primary">
        Additional Areas Needed
      </h3>
      <div class="mt-3 grid md:grid-cols-2 gap-3">
        <div
          v-for="area in additionalAreas"
          :key="area.id"
          :class="[
            'rounded-lg border px-3 py-2',
            severityClass(area.severity),
          ]"
        >
          <div class="text-sm font-medium">{{ area.area }}</div>
          <div class="mt-1 text-xs opacity-80">{{ area.why_it_matters }}</div>
          <div class="mt-2 flex items-center gap-2 flex-wrap">
            <span class="text-[10px] uppercase tracking-wide opacity-75">
              {{ area.status || "open" }}
            </span>
            <span v-if="area.reviewed_at" class="text-[10px] opacity-70">
              {{ fmtDate(area.reviewed_at) }}
            </span>
          </div>
          <textarea
            :value="readinessReviewDraft[area.id]"
            rows="2"
            class="mt-2 w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-xs text-ink-primary focus-ring resize-y"
            placeholder="Rationale"
            @input="emit('update-readiness-review-draft', area.id, $event.target.value)"
          ></textarea>
          <div class="mt-2 flex items-center gap-2 flex-wrap">
            <button
              type="button"
              @click="emit('save-readiness-review', area, 'waived')"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring text-xs"
            >
              <Save class="h-3.5 w-3.5" />
              <span>Waive</span>
            </button>
            <button
              type="button"
              @click="emit('save-readiness-review', area, 'reviewed')"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring text-xs"
            >
              <CheckCircle2 class="h-3.5 w-3.5" />
              <span>Reviewed</span>
            </button>
            <button
              type="button"
              @click="emit('save-readiness-review', area, 'open')"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring text-xs"
            >
              <AlertTriangle class="h-3.5 w-3.5" />
              <span>Reopen</span>
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
