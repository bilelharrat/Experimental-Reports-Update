<script setup>
import { Loader2, Save } from "lucide-vue-next";

defineProps({
  chartSpecsDraft: { type: Array, default: () => [] },
  savingArtifact: { type: String, default: null },
});

const emit = defineEmits(["save-chart-specs"]);

function listItems(value) {
  return Array.isArray(value) ? value : [];
}

function sourceTraceLabel(trace) {
  return trace?.locator || trace?.title || trace?.url || "Source trace";
}

function promptStatus(prompt) {
  if (prompt?.resolved_choice) return prompt.resolved_choice;
  return prompt?.status || (prompt?.required ? "needs review" : "optional");
}
</script>

<template>
  <div class="border border-subtle bg-surface rounded-card p-5">
    <div class="flex items-center justify-between gap-3">
      <h3 class="font-display text-title3 text-ink-primary">
        Chart & Table Plan
      </h3>
      <button
        v-if="chartSpecsDraft.length"
        type="button"
        @click="emit('save-chart-specs')"
        :disabled="Boolean(savingArtifact)"
        class="btn-bordered btn-sm focus-ring"
      >
        <Loader2
          v-if="savingArtifact === 'chart_specs'"
          class="h-3.5 w-3.5 animate-spin"
        />
        <Save v-else class="h-3.5 w-3.5" />
        <span>Save charts</span>
      </button>
    </div>
    <div v-if="chartSpecsDraft.length === 0" class="mt-3 text-sm text-ink-muted">
      No chart specs yet.
    </div>
    <div v-else class="mt-3 space-y-2">
      <div
        v-for="spec in chartSpecsDraft"
        :key="spec.id"
        class="rounded-subbox bg-fill-tertiary p-3"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="text-sm font-medium text-ink-primary">{{ spec.title }}</div>
          <div class="flex items-center gap-2 shrink-0">
            <label class="inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
              <input
                v-model="spec.include_in_final_memo"
                type="checkbox"
                class="h-3.5 w-3.5 rounded border-subtle text-accent focus-ring"
              />
              <span>Final memo</span>
            </label>
            <span
              :class="[ 'text-[10px] rounded px-1.5 py-0.5 uppercase', (spec.source_availability || spec.data_availability) === 'missing' ? 'bg-warning-soft text-warning-ink' : 'bg-success-soft text-success-ink', ]"
            >
              {{ spec.source_availability || spec.data_availability }}
            </span>
          </div>
        </div>
        <div class="mt-1 text-xs text-ink-secondary">
          {{ spec.purpose || spec.takeaway }}
        </div>
        <div class="mt-2 flex flex-wrap gap-2 text-[11px] text-ink-muted">
          <span class="rounded border border-subtle bg-surface px-2 py-0.5">
            {{ spec.recommended_visual_format || "infographic" }}
          </span>
          <span class="rounded border border-subtle bg-surface px-2 py-0.5">
            {{ (spec.image_generation_mode || "no_text_overlay").replaceAll('_', ' ') }}
          </span>
          <span
            v-if="spec.status"
            class="rounded border border-subtle bg-surface px-2 py-0.5"
          >
            {{ spec.status.replaceAll('_', ' ') }}
          </span>
          <span
            v-if="spec.memo_inclusion_decision || spec.final_memo_inclusion_state"
            class="rounded border border-subtle bg-surface px-2 py-0.5"
          >
            {{ (spec.memo_inclusion_decision || spec.final_memo_inclusion_state).replaceAll('_', ' ') }}
          </span>
        </div>
        <div
          v-if="spec.text_overlay_plan"
          class="mt-3 rounded border border-subtle bg-surface px-2 py-1.5 text-xs text-ink-secondary"
        >
          <div class="text-[11px] text-footnote font-semibold text-ink-muted">
            Overlay copy
          </div>
          <div class="mt-1 font-medium text-ink-primary">
            {{ spec.text_overlay_plan.headline }}
          </div>
          <div
            v-if="listItems(spec.text_overlay_plan.callouts).length"
            class="mt-1"
          >
            <span
              v-for="callout in listItems(spec.text_overlay_plan.callouts).slice(0, 4)"
              :key="callout"
              class="mr-2"
            >
              {{ callout }}
            </span>
          </div>
          <div
            v-if="spec.text_overlay_plan.safe_copy_length"
            class="mt-1 text-[11px] text-ink-muted"
          >
            {{ spec.text_overlay_plan.safe_copy_length }}
          </div>
        </div>
        <div
          v-if="listItems(spec.required_metrics).length"
          class="mt-3 text-xs text-ink-secondary"
        >
          <div class="text-[11px] text-footnote font-semibold text-ink-muted">
            Required metrics
          </div>
          <div class="mt-1 grid sm:grid-cols-2 gap-1.5">
            <div
              v-for="metric in listItems(spec.required_metrics).slice(0, 6)"
              :key="metric.id || metric.label"
              class="rounded border border-subtle bg-surface px-2 py-1"
            >
              <div class="font-medium text-ink-primary">{{ metric.label }}</div>
              <div class="text-[11px] text-ink-muted">
                {{ metric.value ?? "missing" }}{{ metric.unit || "" }}
                <span v-if="metric.period"> · {{ metric.period }}</span>
                <span> · {{ metric.source_available ? "sourced" : "source needed" }}</span>
              </div>
            </div>
          </div>
        </div>
        <div
          v-if="listItems(spec.information_gaps).length"
          class="mt-3 text-xs text-warning-ink"
        >
          <div class="text-[11px]">
            Information gaps
          </div>
          <ul class="mt-1 space-y-1">
            <li
              v-for="gap in listItems(spec.information_gaps).slice(0, 5)"
              :key="gap"
            >
              {{ gap }}
            </li>
          </ul>
        </div>
        <div
          v-if="listItems(spec.reviewer_prompts).length"
          class="mt-3 text-xs text-ink-secondary"
        >
          <div class="text-[11px] text-footnote font-semibold text-ink-muted">
            Operator review notes
          </div>
          <div
            v-for="prompt in listItems(spec.reviewer_prompts).slice(0, 4)"
            :key="prompt.id || prompt.prompt"
            class="mt-1 rounded border border-subtle bg-surface px-2 py-1"
          >
            <div class="font-medium text-ink-primary">{{ prompt.prompt }}</div>
            <div class="text-[11px] text-ink-muted">
              {{ promptStatus(prompt) }}
            </div>
          </div>
        </div>
        <div
          v-if="listItems(spec.source_traces).length"
          class="mt-3 text-xs text-ink-secondary"
        >
          <div class="text-[11px] text-footnote font-semibold text-ink-muted">
            Source evidence
          </div>
          <div
            v-for="trace in listItems(spec.source_traces).slice(0, 3)"
            :key="sourceTraceLabel(trace)"
            class="mt-1 rounded border border-subtle bg-surface px-2 py-1"
          >
            <div class="text-[11px] text-ink-muted">
              {{ sourceTraceLabel(trace) }}
              <span v-if="trace.confidence">· {{ trace.confidence }}</span>
            </div>
            <div>{{ trace.excerpt }}</div>
          </div>
        </div>
        <div
          v-if="spec.design_prompt?.composition"
          class="mt-3 text-xs text-ink-secondary"
        >
          <div class="text-[11px] text-footnote font-semibold text-ink-muted">
            Image prompt
          </div>
          <div class="mt-1 rounded border border-subtle bg-surface px-2 py-1">
            {{ spec.design_prompt.composition }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
