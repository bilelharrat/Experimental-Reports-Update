<script setup>
import { computed, ref } from "vue";
import { ArrowDown, ArrowUp, Loader2, Save } from "lucide-vue-next";
import { useT } from "../../i18n.js";

const props = defineProps({
  risks: { type: Array, default: () => [] },
  prioritizedRisks: { type: Array, default: () => [] },
  riskDraft: { type: Array, default: () => [] },
  riskDraftDirty: { type: Boolean, default: false },
  riskPriorityMap: { type: [Object, Map], default: () => new Map() },
  riskPriorityDraft: { type: Array, default: () => [] },
  savingArtifact: { type: String, default: null },
  refiningRiskId: { type: String, default: null },
  canMoveRisk: { type: Function, default: () => false },
});

const emit = defineEmits([
  "update-risk-field",
  "save-risk-cards",
  "save-risk-priorities",
  "move-risk-priority",
  "set-risk-selected",
  "set-risk-disposition",
  "refine-risk",
]);

const t = useT();
const expandedId = ref(null);
const noteByRisk = ref({});
const framingByRisk = ref({});

const FRAMINGS = [
  "technology",
  "market_structure",
  "competitive_moat",
  "go_to_market",
  "financial",
  "regulatory",
  "other",
];
const DISPOSITIONS = [
  "lead_risk",
  "downside_trigger",
  "valuation_sensitivity",
  "monitoring",
  "dismissed",
];

const activeId = computed(() => expandedId.value || props.prioritizedRisks[0]?.id || null);

function priorityRow(riskId) {
  return props.riskPriorityMap.get(riskId) || {};
}

function cardRisk(risk) {
  return props.riskDraft.find((item) => item?.id === risk?.id) || risk;
}

function updateRiskField(riskId, field, value) {
  emit("update-risk-field", riskId, field, value);
}

function isExpanded(riskId) {
  return activeId.value === riskId;
}

function toggleExpanded(riskId) {
  expandedId.value = expandedId.value === riskId ? null : riskId;
}

function currentFraming(risk) {
  return (
    framingByRisk.value[risk.id]
    || priorityRow(risk.id).framing
    || risk.framing
    || "other"
  );
}

function currentNote(risk) {
  if (Object.prototype.hasOwnProperty.call(noteByRisk.value, risk.id)) {
    return noteByRisk.value[risk.id];
  }
  return priorityRow(risk.id).analyst_note || risk.analyst_note || "";
}

function setNote(riskId, value) {
  noteByRisk.value = { ...noteByRisk.value, [riskId]: value };
}

function setFraming(riskId, value) {
  framingByRisk.value = { ...framingByRisk.value, [riskId]: value };
}

function listItems(value) {
  return Array.isArray(value) ? value.filter((item) => item) : [];
}

function evidenceItems(value) {
  return listItems(value).map((item) => (
    typeof item === "string"
      ? { excerpt: item, source_class: "inference" }
      : item
  ));
}

function sourceClassLabel(value) {
  const key = `risk.source_class.${value || "inference"}`;
  const label = t(key);
  return label === key ? t("risk.source_class.inference") : label;
}
</script>

<template>
  <div class="border border-subtle bg-surface rounded-card p-5">
    <div class="flex items-center justify-between gap-3">
      <h3 class="font-display text-title3 text-ink-primary">
        {{ t("risk.board_title") }}
      </h3>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <button
          v-if="riskDraftDirty"
          type="button"
          @click="emit('save-risk-cards')"
          :disabled="Boolean(savingArtifact)"
          class="btn-bordered btn-sm focus-ring"
        >
          <Loader2
            v-if="savingArtifact === 'strategic_risks'"
            class="h-3.5 w-3.5 animate-spin"
          />
          <Save v-else class="h-3.5 w-3.5" />
          <span>{{ t("risk.save_cards") }}</span>
        </button>
        <button
          v-if="riskPriorityDraft.length"
          type="button"
          @click="emit('save-risk-priorities')"
          :disabled="Boolean(savingArtifact)"
          class="btn-bordered btn-sm focus-ring"
        >
          <Loader2
            v-if="savingArtifact === 'risk_priorities'"
            class="h-3.5 w-3.5 animate-spin"
          />
          <Save v-else class="h-3.5 w-3.5" />
          <span>{{ t("risk.save_priorities") }}</span>
        </button>
      </div>
    </div>
    <div v-if="risks.length === 0" class="mt-3 text-sm text-ink-muted">
      {{ t("risk.empty") }}
    </div>
    <div v-else class="mt-3 space-y-3">
      <div
        v-for="risk in prioritizedRisks"
        :key="risk.id"
        class="rounded-subbox bg-fill-tertiary p-3"
      >
        <div class="flex items-start gap-3">
          <div class="flex w-8 shrink-0 flex-col items-center gap-1">
            <button
              type="button"
              @click="emit('move-risk-priority', risk.id, -1)"
              :disabled="!canMoveRisk(risk.id, -1) || Boolean(savingArtifact)"
              class="btn-bordered h-7 w-7 text-ink-muted hover:text-ink-primary disabled:opacity-35 disabled:cursor-not-allowed focus-ring"
              :title="t('risk.move_up')"
            >
              <ArrowUp class="h-3.5 w-3.5" />
            </button>
            <div class="text-[11px] font-mono text-ink-muted">
              #{{ priorityRow(risk.id).rank || "—" }}
            </div>
            <button
              type="button"
              @click="emit('move-risk-priority', risk.id, 1)"
              :disabled="!canMoveRisk(risk.id, 1) || Boolean(savingArtifact)"
              class="btn-bordered h-7 w-7 text-ink-muted hover:text-ink-primary disabled:opacity-35 disabled:cursor-not-allowed focus-ring"
              :title="t('risk.move_down')"
            >
              <ArrowDown class="h-3.5 w-3.5" />
            </button>
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-start justify-between gap-3">
              <button
                type="button"
                class="text-left font-medium text-ink-primary hover:text-accent focus-ring"
                @click="toggleExpanded(risk.id)"
              >
                {{ cardRisk(risk).title }}
              </button>
              <div class="flex flex-wrap items-center justify-end gap-1.5">
                <span
                  v-if="priorityRow(risk.id).human_ranked"
                  class="text-caption1 text-accent"
                >
                  {{ t("risk.human_ranked") }}
                </span>
                <span
                  v-if="risk.generated_by === 'deterministic_fallback'"
                  class="text-caption1 text-ink-muted"
                >
                  {{ t("risk.fallback_badge") }}
                </span>
                <span
                  v-else-if="risk.generated_by === 'claude_code'"
                  class="text-caption1 text-ink-muted"
                >
                  {{ t("risk.claude_badge") }}
                </span>
                <span class="text-caption1 text-ink-muted">
                  {{ risk.status }}
                </span>
              </div>
            </div>
            <div class="mt-1 text-sm text-ink-secondary">
              {{ cardRisk(risk).decision_question }}
            </div>
            <div class="mt-2 text-xs text-ink-muted">
              {{ cardRisk(risk).why_it_matters }}
            </div>
            <div class="mt-2 flex flex-wrap gap-2 text-[11px] text-ink-muted">
              <span>{{ t("risk.severity") }}: {{ risk.severity || "medium" }}</span>
              <span>{{ t("risk.likelihood") }}: {{ risk.likelihood || "medium" }}</span>
            </div>
            <div v-if="isExpanded(risk.id)" class="mt-3 space-y-3">
              <div class="grid gap-3 md:grid-cols-2">
                <div class="rounded-md border border-subtle bg-surface p-3">
                  <div class="text-[11px] font-semibold text-ink-muted">
                    {{ t("risk.bull") }}
                  </div>
                  <div class="mt-1 text-sm text-ink-secondary">
                    {{ risk.bull_case_answer }}
                  </div>
                </div>
                <div class="rounded-md border border-subtle bg-surface p-3">
                  <div class="text-[11px] font-semibold text-ink-muted">
                    {{ t("risk.bear") }}
                  </div>
                  <div class="mt-1 text-sm text-ink-secondary">
                    {{ risk.bear_case_answer }}
                  </div>
                </div>
              </div>
              <div v-if="cardRisk(risk).description && cardRisk(risk).description !== cardRisk(risk).why_it_matters" class="text-sm text-ink-secondary">
                {{ risk.description }}
              </div>
              <div v-if="risk.materiality" class="text-xs text-ink-muted">
                <span class="font-semibold">{{ t("risk.materiality") }}:</span>
                {{ risk.materiality }}
              </div>
              <div v-if="listItems(risk.key_questions).length">
                <div class="text-[11px] font-semibold text-ink-muted">
                  {{ t("risk.questions") }}
                </div>
                <ul class="mt-1 list-disc space-y-1 pl-4 text-sm text-ink-secondary">
                  <li v-for="item in listItems(risk.key_questions)" :key="item">
                    {{ item }}
                  </li>
                </ul>
              </div>
              <div class="grid gap-3 md:grid-cols-2">
                <div>
                  <div class="text-[11px] font-semibold text-ink-muted">
                    {{ t("risk.evidence_needed") }}
                  </div>
                  <ul class="mt-1 list-disc space-y-1 pl-4 text-sm text-ink-secondary">
                    <li v-for="item in listItems(risk.evidence_needed)" :key="item">
                      {{ item }}
                    </li>
                  </ul>
                </div>
                <div>
                  <div class="text-[11px] font-semibold text-ink-muted">
                    {{ t("risk.sources") }}
                  </div>
                  <ul class="mt-1 list-disc space-y-1 pl-4 text-sm text-ink-secondary">
                    <li v-for="item in listItems(risk.best_sources)" :key="item">
                      {{ item }}
                    </li>
                  </ul>
                </div>
              </div>
              <div class="grid gap-3 md:grid-cols-2">
                <div>
                  <div class="text-[11px] font-semibold text-ink-muted">
                    {{ t("risk.supporting") }}
                  </div>
                  <ul class="mt-1 space-y-2 text-sm text-ink-secondary">
                    <li
                      v-for="(item, index) in evidenceItems(risk.supporting_evidence)"
                      :key="`${item.excerpt}-${index}`"
                    >
                      <span class="text-[11px] uppercase tracking-wide text-ink-muted">
                        {{ sourceClassLabel(item.source_class) }}
                      </span>
                      <span v-if="item.locator || item.filename" class="text-ink-muted">
                        {{ item.locator || item.filename }}:
                      </span>
                      {{ item.excerpt }}
                    </li>
                    <li
                      v-if="evidenceItems(risk.supporting_evidence).length === 0"
                      class="text-ink-muted"
                    >
                      {{ t("risk.no_evidence") }}
                    </li>
                  </ul>
                </div>
                <div>
                  <div class="text-[11px] font-semibold text-ink-muted">
                    {{ t("risk.contradicting") }}
                  </div>
                  <ul class="mt-1 space-y-2 text-sm text-ink-secondary">
                    <li
                      v-for="(item, index) in evidenceItems(risk.contradicting_evidence)"
                      :key="`${item.excerpt}-${index}`"
                    >
                      <span class="text-[11px] uppercase tracking-wide text-ink-muted">
                        {{ sourceClassLabel(item.source_class) }}
                      </span>
                      <span v-if="item.locator || item.filename" class="text-ink-muted">
                        {{ item.locator || item.filename }}:
                      </span>
                      {{ item.excerpt }}
                    </li>
                    <li
                      v-if="evidenceItems(risk.contradicting_evidence).length === 0"
                      class="text-ink-muted"
                    >
                      {{ t("risk.no_evidence") }}
                    </li>
                  </ul>
                </div>
              </div>
              <div class="grid gap-3 md:grid-cols-2">
                <div>
                  <div class="text-[11px] font-semibold text-ink-muted">
                    {{ t("risk.missing") }}
                  </div>
                  <ul class="mt-1 list-disc space-y-1 pl-4 text-sm text-ink-secondary">
                    <li v-for="item in listItems(risk.missing_evidence)" :key="item">
                      {{ item }}
                    </li>
                    <li
                      v-if="listItems(risk.missing_evidence).length === 0"
                      class="text-ink-muted"
                    >
                      {{ t("risk.no_evidence") }}
                    </li>
                  </ul>
                </div>
                <div>
                  <div class="text-[11px] font-semibold text-ink-muted">
                    {{ t("risk.would_change") }}
                  </div>
                  <ul class="mt-1 list-disc space-y-1 pl-4 text-sm text-ink-secondary">
                    <li
                      v-for="item in listItems(risk.evidence_that_would_change_assessment)"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                  </ul>
                </div>
              </div>
              <div v-if="risk.mitigation_or_monitoring" class="text-sm text-ink-secondary">
                <span class="text-[11px] font-semibold text-ink-muted">
                  {{ t("risk.mitigation") }}:
                </span>
                {{ risk.mitigation_or_monitoring }}
              </div>
              <div>
                <label class="text-[11px] font-semibold text-ink-muted" :for="`risk-disposition-${risk.id}`">
                  {{ t("risk.disposition") }}
                </label>
                <select
                  :id="`risk-disposition-${risk.id}`"
                  class="mt-1 w-full rounded-md border border-subtle bg-surface px-2 py-1 text-sm focus-ring"
                  :value="priorityRow(risk.id).disposition || risk.suggested_posture || 'monitoring'"
                  :disabled="Boolean(savingArtifact)"
                  @change="emit('set-risk-disposition', risk.id, $event.target.value)"
                >
                  <option v-for="item in DISPOSITIONS" :key="item" :value="item">
                    {{ t(`risk.disposition.${item}`) }}
                  </option>
                </select>
              </div>
              <div class="rounded-md border border-subtle bg-surface p-3">
                <div class="text-[11px] font-semibold text-ink-muted">
                  {{ t("risk.edit_card") }}
                </div>
                <div class="mt-2 space-y-2">
                  <label class="block text-[11px] font-semibold text-ink-muted" :for="`risk-title-${risk.id}`">
                    {{ t("risk.title") }}
                  </label>
                  <input
                    :id="`risk-title-${risk.id}`"
                    :value="cardRisk(risk).title"
                    class="field focus-ring"
                    @input="updateRiskField(risk.id, 'title', $event.target.value)"
                  />
                  <label class="block text-[11px] font-semibold text-ink-muted" :for="`risk-question-${risk.id}`">
                    {{ t("risk.decision_question") }}
                  </label>
                  <textarea
                    :id="`risk-question-${risk.id}`"
                    :value="cardRisk(risk).decision_question"
                    rows="2"
                    class="field resize-y focus-ring"
                    @input="updateRiskField(risk.id, 'decision_question', $event.target.value)"
                  ></textarea>
                  <label class="block text-[11px] font-semibold text-ink-muted" :for="`risk-why-${risk.id}`">
                    {{ t("risk.why") }}
                  </label>
                  <textarea
                    :id="`risk-why-${risk.id}`"
                    :value="cardRisk(risk).why_it_matters"
                    rows="3"
                    class="field resize-y focus-ring"
                    @input="updateRiskField(risk.id, 'why_it_matters', $event.target.value)"
                  ></textarea>
                  <label class="block text-[11px] font-semibold text-ink-muted" :for="`risk-watch-${risk.id}`">
                    {{ t("risk.what_watch") }}
                  </label>
                  <textarea
                    :id="`risk-watch-${risk.id}`"
                    :value="cardRisk(risk).mitigation_or_monitoring"
                    rows="2"
                    class="field resize-y focus-ring"
                    @input="updateRiskField(risk.id, 'mitigation_or_monitoring', $event.target.value)"
                  ></textarea>
                </div>
              </div>
              <div class="rounded-md border border-subtle bg-surface p-3">
                <div class="text-[11px] font-semibold text-ink-muted">
                  {{ t("risk.framing_prompt") }}
                </div>
                <div class="mt-1 text-xs text-ink-muted">
                  {{ t("risk.framing_help") }}
                </div>
                <div class="mt-2 flex flex-wrap gap-1.5">
                  <button
                    v-for="item in FRAMINGS"
                    :key="item"
                    type="button"
                    class="btn-bordered btn-sm focus-ring"
                    :class="currentFraming(risk) === item ? 'border-accent text-accent' : ''"
                    :disabled="Boolean(savingArtifact) || Boolean(refiningRiskId)"
                    @click="setFraming(risk.id, item)"
                  >
                    {{ t(`risk.framing.${item}`) }}
                  </button>
                </div>
                <label class="mt-3 block text-[11px] font-semibold text-ink-muted" :for="`risk-note-${risk.id}`">
                  {{ t("risk.analyst_note") }}
                </label>
                <textarea
                  :id="`risk-note-${risk.id}`"
                  class="mt-1 w-full rounded-md border border-subtle bg-fill-tertiary px-2 py-1 text-sm focus-ring"
                  rows="2"
                  :placeholder="t('risk.analyst_note_placeholder')"
                  :value="currentNote(risk)"
                  @input="setNote(risk.id, $event.target.value)"
                />
                <button
                  type="button"
                  class="btn-bordered btn-sm mt-2 focus-ring"
                  :disabled="Boolean(savingArtifact) || Boolean(refiningRiskId)"
                  @click="emit('refine-risk', risk.id, currentFraming(risk), currentNote(risk))"
                >
                  <Loader2
                    v-if="refiningRiskId === risk.id"
                    class="h-3.5 w-3.5 animate-spin"
                  />
                  <span>{{ t("risk.refine") }}</span>
                </button>
              </div>
            </div>
          </div>
          <label class="shrink-0 inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
            <input
              type="checkbox"
              :checked="Boolean(priorityRow(risk.id).selected)"
              @change="emit('set-risk-selected', risk.id, $event.target.checked)"
              :disabled="Boolean(savingArtifact)"
              class="h-3.5 w-3.5 rounded border-subtle text-accent focus-ring"
            />
            <span>{{ t("risk.research") }}</span>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>
