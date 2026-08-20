<script setup>
defineProps({
  sourceBrief: { type: Object, default: null },
});

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
  <div class="xl:col-span-2 border border-subtle bg-surface rounded-card p-5">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h3 class="font-display text-title3 text-ink-primary">
          Infographic Source Brief
        </h3>
        <div v-if="sourceBrief?.confidence" class="mt-1 text-xs text-ink-muted">
          Confidence: {{ sourceBrief.confidence }}
        </div>
      </div>
      <span
        v-if="sourceBrief?.generated_by"
        class="rounded bg-surface-muted px-2 py-1 text-caption1 text-ink-muted"
      >
        {{ sourceBrief.generated_by.replaceAll('_', ' ') }}
      </span>
    </div>
    <div v-if="!sourceBrief" class="mt-3 text-sm text-ink-muted">
      No infographic source brief yet.
    </div>
    <template v-else>
      <p v-if="sourceBrief.summary" class="mt-3 text-sm text-ink-secondary">
        {{ sourceBrief.summary }}
      </p>
      <div class="mt-4 grid xl:grid-cols-3 gap-3">
        <div class="rounded-subbox bg-fill-tertiary p-3">
          <div class="text-footnote font-semibold text-ink-muted">
            Claims
          </div>
          <div
            v-for="claim in listItems(sourceBrief.compact_claims).slice(0, 6)"
            :key="claim.id || claim.claim"
            class="mt-2 rounded border border-subtle bg-surface px-2 py-1.5 text-xs"
          >
            <div class="font-medium text-ink-primary">{{ claim.claim }}</div>
            <div class="mt-1 text-[11px] text-ink-muted">
              {{ claim.evidence_status || "needs review" }} · {{ claim.confidence || "medium" }}
              <span v-if="claim.prohibited_for_visuals"> · no visual fact claim</span>
            </div>
            <div
              v-for="trace in listItems(claim.source_traces).slice(0, 2)"
              :key="`${claim.id}-${sourceTraceLabel(trace)}`"
              class="mt-1 text-[11px] text-ink-secondary"
            >
              <span class="text-ink-muted">{{ sourceTraceLabel(trace) }}:</span>
              {{ trace.excerpt }}
            </div>
          </div>
        </div>
        <div class="rounded-subbox bg-fill-tertiary p-3">
          <div class="text-footnote font-semibold text-ink-muted">
            Metrics & Warnings
          </div>
          <div
            v-for="metric in listItems(sourceBrief.numeric_metrics).slice(0, 6)"
            :key="metric.id || metric.label"
            class="mt-2 text-xs text-ink-secondary"
          >
            <span class="font-medium text-ink-primary">{{ metric.label }}</span>
            <span>
              · {{ metric.value ?? "missing" }}{{ metric.unit || "" }}
            </span>
            <span v-if="metric.period"> · {{ metric.period }}</span>
          </div>
          <div v-if="listItems(sourceBrief.missing_evidence).length" class="mt-3">
            <div class="text-[11px] text-warning-ink">
              Missing evidence
            </div>
            <ul class="mt-1 space-y-1 text-xs text-ink-secondary">
              <li
                v-for="item in listItems(sourceBrief.missing_evidence).slice(0, 5)"
                :key="item"
              >
                {{ item }}
              </li>
            </ul>
          </div>
          <div v-if="listItems(sourceBrief.no_go_claims).length" class="mt-3">
            <div class="text-[11px] text-danger">
              Unsupported visual claims
            </div>
            <ul class="mt-1 space-y-1 text-xs text-ink-secondary">
              <li
                v-for="item in listItems(sourceBrief.no_go_claims).slice(0, 5)"
                :key="item"
              >
                {{ item }}
              </li>
            </ul>
          </div>
        </div>
        <div class="rounded-subbox bg-fill-tertiary p-3">
          <div class="text-footnote font-semibold text-ink-muted">
            Opportunities & Prompts
          </div>
          <div
            v-for="item in listItems(sourceBrief.visual_opportunities).slice(0, 4)"
            :key="item.id || item.title"
            class="mt-2 text-xs text-ink-secondary"
          >
            <div class="font-medium text-ink-primary">{{ item.title }}</div>
            <div>{{ item.rationale }}</div>
          </div>
          <div
            v-for="prompt in listItems(sourceBrief.reviewer_prompts).slice(0, 4)"
            :key="prompt.id || prompt.prompt"
            class="mt-2 rounded border border-subtle bg-surface px-2 py-1 text-xs text-ink-secondary"
          >
            <div class="font-medium text-ink-primary">{{ prompt.prompt }}</div>
            <div class="mt-1 text-[11px] text-ink-muted">
              {{ promptStatus(prompt) }}
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
