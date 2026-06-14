<script setup>
import { Loader2, Save } from "lucide-vue-next";

defineProps({
  narrativeDraft: { type: Object, default: null },
  sessionId: { type: String, default: "session" },
  savingArtifact: { type: String, default: null },
});

const emit = defineEmits(["save-narrative"]);

function listItems(value) {
  return Array.isArray(value) ? value : [];
}

function promptStatus(prompt) {
  if (prompt?.resolved_choice) return prompt.resolved_choice;
  return prompt?.status || (prompt?.required ? "needs review" : "optional");
}
</script>

<template>
  <div class="border border-subtle bg-surface rounded-card p-5">
    <div class="flex items-center justify-between gap-3">
      <h3 class="font-display text-lg font-semibold text-ink-primary">
        Narrative Hooks
      </h3>
      <button
        v-if="narrativeDraft"
        type="button"
        @click="emit('save-narrative')"
        :disabled="Boolean(savingArtifact)"
        class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
      >
        <Loader2
          v-if="savingArtifact === 'narrative_hooks'"
          class="h-3.5 w-3.5 animate-spin"
        />
        <Save v-else class="h-3.5 w-3.5" />
        <span>Save hooks</span>
      </button>
    </div>
    <div v-if="!narrativeDraft" class="mt-3 text-sm text-ink-muted">
      No openings or endings yet.
    </div>
    <template v-else>
      <div class="mt-3 text-xs uppercase tracking-wide text-ink-muted">
        Openings
      </div>
      <div class="mt-2 space-y-2">
        <label
          v-for="opening in narrativeDraft.openings"
          :key="opening.id"
          :class="[
            'flex items-start gap-3 rounded-lg border p-3 text-sm cursor-pointer',
            narrativeDraft.selected_opening_id === opening.id
              ? 'border-accent bg-accent-soft/40 text-accent-ink'
              : 'border-subtle bg-surface-muted text-ink-primary',
          ]"
        >
          <input
            v-model="narrativeDraft.selected_opening_id"
            type="radio"
            :name="`opening-${sessionId}`"
            :value="opening.id"
            class="mt-0.5 h-4 w-4 border-subtle text-accent focus-ring"
          />
          <span class="min-w-0">
            <span class="block">{{ opening.text }}</span>
            <span class="mt-1 flex flex-wrap gap-2 text-[11px] text-ink-muted">
              <span>{{ opening.tone }}</span>
              <span v-if="opening.confidence">· {{ opening.confidence }}</span>
              <span v-if="opening.status">· {{ opening.status.replaceAll('_', ' ') }}</span>
            </span>
            <span
              v-if="opening.overclaiming_risk"
              class="mt-1 block text-[11px] text-warning-ink"
            >
              {{ opening.overclaiming_risk }}
            </span>
            <span
              v-if="listItems(opening.paired_infographic_ids).length"
              class="mt-1 block text-[11px] text-ink-muted"
            >
              Paired visuals: {{ listItems(opening.paired_infographic_ids).join(", ") }}
            </span>
          </span>
        </label>
      </div>
      <div
        v-if="listItems(narrativeDraft.transitions).length"
        class="mt-4 text-xs uppercase tracking-wide text-ink-muted"
      >
        Transitions
      </div>
      <div
        v-if="listItems(narrativeDraft.transitions).length"
        class="mt-2 space-y-2"
      >
        <label
          v-for="transition in narrativeDraft.transitions"
          :key="transition.id"
          :class="[
            'flex items-start gap-3 rounded-lg border p-3 text-sm cursor-pointer',
            narrativeDraft.selected_transition_id === transition.id
              ? 'border-accent bg-accent-soft/40 text-accent-ink'
              : 'border-subtle bg-surface-muted text-ink-primary',
          ]"
        >
          <input
            v-model="narrativeDraft.selected_transition_id"
            type="radio"
            :name="`transition-${sessionId}`"
            :value="transition.id"
            class="mt-0.5 h-4 w-4 border-subtle text-accent focus-ring"
          />
          <span class="min-w-0">
            <span class="block">{{ transition.text }}</span>
            <span class="mt-1 flex flex-wrap gap-2 text-[11px] text-ink-muted">
              <span>{{ transition.tone }}</span>
              <span v-if="transition.confidence">· {{ transition.confidence }}</span>
              <span v-if="transition.status">· {{ transition.status.replaceAll('_', ' ') }}</span>
            </span>
            <span
              v-if="transition.overclaiming_risk"
              class="mt-1 block text-[11px] text-warning-ink"
            >
              {{ transition.overclaiming_risk }}
            </span>
          </span>
        </label>
      </div>
      <div class="mt-4 text-xs uppercase tracking-wide text-ink-muted">
        Endings
      </div>
      <div class="mt-2 space-y-2">
        <label
          v-for="ending in narrativeDraft.endings"
          :key="ending.id"
          :class="[
            'flex items-start gap-3 rounded-lg border p-3 text-sm cursor-pointer',
            narrativeDraft.selected_ending_id === ending.id
              ? 'border-accent bg-accent-soft/40 text-accent-ink'
              : 'border-subtle bg-surface-muted text-ink-primary',
          ]"
        >
          <input
            v-model="narrativeDraft.selected_ending_id"
            type="radio"
            :name="`ending-${sessionId}`"
            :value="ending.id"
            class="mt-0.5 h-4 w-4 border-subtle text-accent focus-ring"
          />
          <span class="min-w-0">
            <span class="block">{{ ending.text }}</span>
            <span class="mt-1 flex flex-wrap gap-2 text-[11px] text-ink-muted">
              <span>{{ ending.tone }}</span>
              <span v-if="ending.confidence">· {{ ending.confidence }}</span>
              <span v-if="ending.status">· {{ ending.status.replaceAll('_', ' ') }}</span>
            </span>
            <span
              v-if="ending.overclaiming_risk"
              class="mt-1 block text-[11px] text-warning-ink"
            >
              {{ ending.overclaiming_risk }}
            </span>
          </span>
        </label>
      </div>
      <div
        v-if="listItems(narrativeDraft.reviewer_prompts).length"
        class="mt-4 rounded-lg border border-subtle bg-surface-muted p-3 text-xs text-ink-secondary"
      >
        <div class="text-[11px] uppercase tracking-wide text-ink-muted">
          Reviewer prompts
        </div>
        <div
          v-for="prompt in listItems(narrativeDraft.reviewer_prompts)"
          :key="prompt.id || prompt.prompt"
          class="mt-2 rounded border border-subtle bg-surface px-2 py-1"
        >
          <div class="font-medium text-ink-primary">{{ prompt.prompt }}</div>
          <div class="mt-1 text-[11px] text-ink-muted">
            {{ promptStatus(prompt) }}
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
