<script setup>
// Web twin of MacDealPipelineView.swift: card header with warmth pill and
// deal lead, the equal-width stage stepper (16pt circles: accent current,
// green past with checkmark), and the intro/touchpoint/next-step tile row.
import { nextTick, ref, watch } from "vue";
import { useT } from "../../i18n.js";
import {
  Waypoints,
  CircleUser,
  Link2,
  MessageSquare,
  CalendarClock,
  Check,
  AlertTriangle,
} from "lucide-vue-next";
import api from "../../api.js";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
  company: {
    type: Object,
    default: () => ({}),
  },
});

const emit = defineEmits(["stage-updated"]);
const t = useT();

const defaultStages = [
  "Sourced",
  "Partner Intro",
  "Technical Diligence",
  "Term Sheet / IC",
  "Portfolio",
];

const loading = ref(false);
const saving = ref(false);
const saveError = ref(null);
const loadAttempted = ref(false);
const pipeline = ref(null);

async function loadPipeline() {
  if (!props.companyId) return;
  loading.value = true;
  saveError.value = null;
  loadAttempted.value = false;
  pipeline.value = null;
  try {
    const res = await api.getDealPipeline(props.companyId);
    if (res) {
      pipeline.value = {
        ...res,
        stages: res.stages?.length ? res.stages : defaultStages,
      };
    }
  } catch {
    // loadAttempted with a null pipeline renders the retry row
  } finally {
    loading.value = false;
    loadAttempted.value = true;
  }
}

watch(() => props.companyId, loadPipeline, { immediate: true });

function stages() {
  return pipeline.value?.stages || defaultStages;
}

function stageIndex(stage) {
  return stages().indexOf(stage);
}

function currentStage() {
  return pipeline.value?.stage || "Sourced";
}

// ---- Intro path · last touchpoint · next step, edited in place ----------
// All three were "Not recorded" on every company because the card only ever
// displayed them; the API has accepted edits all along.
const editingField = ref("");
const draft = ref("");
const draftDue = ref("");
const fieldSaving = ref(false);
const editorRef = ref(null);

async function startEdit(field) {
  if (!pipeline.value || fieldSaving.value) return;
  editingField.value = field;
  draft.value = pipeline.value[field] || "";
  draftDue.value = field === "next_step" ? pipeline.value.next_step_due || "" : "";
  saveError.value = null;
  await nextTick();
  const el = Array.isArray(editorRef.value) ? editorRef.value[0] : editorRef.value;
  el?.focus();
}

function cancelEdit() {
  editingField.value = "";
}

async function saveEdit() {
  const field = editingField.value;
  if (!field || fieldSaving.value) return;
  const payload = { [field]: draft.value.trim() || null };
  if (field === "next_step") payload.next_step_due = draftDue.value || null;
  fieldSaving.value = true;
  saveError.value = null;
  try {
    const res = await api.updateDealPipeline(props.companyId, payload);
    if (res) {
      pipeline.value = { ...res, stages: res.stages?.length ? res.stages : defaultStages };
    }
    editingField.value = "";
  } catch (err) {
    saveError.value = t("research_desk.pipeline_field_save_failed", {
      reason: err?.message || String(err),
    });
  } finally {
    fieldSaving.value = false;
  }
}

function onEditorKeydown(event) {
  if (event.key === "Escape") {
    event.preventDefault();
    cancelEdit();
  } else if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    saveEdit();
  }
}

async function changeStage(newStage) {
  if (saving.value || !pipeline.value || pipeline.value.stage === newStage) return;
  const previous = { ...pipeline.value };
  pipeline.value.stage = newStage;
  pipeline.value.days_in_stage = 0;
  saving.value = true;
  saveError.value = null;

  try {
    const res = await api.updateDealPipeline(props.companyId, { stage: newStage });
    if (res) {
      pipeline.value = {
        ...res,
        stages: res.stages?.length ? res.stages : defaultStages,
      };
    }
    emit("stage-updated", newStage);
  } catch (err) {
    pipeline.value = previous;
    saveError.value = `Stage change wasn't saved: ${err?.message || err}`;
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-4">
    <!-- MacCardHeader("Deal pipeline", …) + warmth pill + deal lead -->
    <div class="mac-cardheader">
      <span class="mac-cardheader-icon"><Waypoints class="h-[13px] w-[13px]" stroke-width="2.4" /></span>
      <div class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-headline">{{ t("research_desk.deal_pipeline") }}</span>
        <span class="mac-t-caption mac-c-secondary">{{ t("research_desk.deal_pipeline_subtitle") }}</span>
      </div>
      <span class="min-w-2 flex-1" />
      <span
        v-if="pipeline?.warmth_score != null"
        class="mac-status-pill shrink-0"
        :style="{ '--tint': pipeline.warmth_score >= 80 ? 'var(--mac-green)' : 'var(--mac-orange)' }"
      >
        {{ t("research_desk.warmth_label") }} {{ pipeline.warmth_score }}
      </span>
      <span v-if="pipeline?.deal_lead" class="mac-t-caption mac-c-secondary flex shrink-0 items-center gap-1">
        <CircleUser class="h-3 w-3" />
        {{ pipeline.deal_lead }}
      </span>
    </div>

    <!-- Stage stepper -->
    <div class="flex flex-col gap-1.5">
      <div class="flex items-center">
        <span class="mac-t-label mac-c-secondary">{{ t("research_desk.current_stage") }}</span>
        <span class="flex-1" />
        <span v-if="pipeline" class="mac-t-caption mac-mono mac-c-tertiary">
          {{ pipeline.days_in_stage ?? 0 }} {{ t("research_desk.days_in") }} {{ currentStage() }}
        </span>
      </div>

      <div v-if="!pipeline && loadAttempted" class="flex items-center gap-2">
        <AlertTriangle class="h-3.5 w-3.5" :style="{ color: 'var(--mac-orange)' }" />
        <span class="mac-t-caption mac-c-secondary">{{ t("research_desk.pipeline_load_failed") }}</span>
        <button type="button" class="mac-btn mac-btn--sm" @click="loadPipeline">
          {{ t("research_desk.retry") }}
        </button>
      </div>
      <div v-else-if="!pipeline" class="flex items-center gap-2">
        <span class="mac-spinner" />
        <span class="mac-t-caption mac-c-secondary">{{ t("research_desk.loading_pipeline") }}</span>
      </div>
      <template v-else>
        <div class="grid grid-cols-2 gap-1.5 sm:grid-cols-5">
          <button
            v-for="(stage, idx) in stages()"
            :key="stage"
            type="button"
            class="flex items-center gap-1.5 px-2.5 py-2 text-left"
            :class="stage === currentStage() || stageIndex(stage) < stageIndex(currentStage()) ? 'mac-tile-tint' : 'mac-tile'"
            :style="
              stage === currentStage()
                ? { '--tint': 'var(--mac-accent)' }
                : stageIndex(stage) < stageIndex(currentStage())
                  ? { '--tint': 'var(--mac-green)' }
                  : {}
            "
            :disabled="saving || stage === currentStage()"
            :title="`Move ${company?.name || companyId} to ${stage}`"
            @click="changeStage(stage)"
          >
            <!-- 16pt indicator circle -->
            <span
              class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
              :style="
                stage === currentStage()
                  ? { background: 'var(--mac-accent)', color: '#fff' }
                  : stageIndex(stage) < stageIndex(currentStage())
                    ? { background: 'var(--mac-green)', color: '#fff' }
                    : { background: 'color-mix(in srgb, var(--mac-secondary) 20%, transparent)', color: 'var(--mac-secondary)' }
              "
            >
              <Check v-if="stageIndex(stage) < stageIndex(currentStage())" class="h-2.5 w-2.5" stroke-width="3" />
              <template v-else>{{ idx + 1 }}</template>
            </span>

            <span
              class="truncate text-[11px]"
              :style="
                stage === currentStage()
                  ? { fontWeight: 700, color: 'var(--mac-accent)' }
                  : stageIndex(stage) < stageIndex(currentStage())
                    ? { fontWeight: 500, color: 'var(--mac-label)' }
                    : { fontWeight: 500, color: 'var(--mac-secondary)' }
              "
            >
              {{ stage }}
            </span>
          </button>
        </div>

        <div v-if="saveError" class="flex items-center gap-1.5">
          <AlertTriangle class="h-3.5 w-3.5" :style="{ color: 'var(--mac-red)' }" />
          <span class="mac-t-caption" :style="{ color: 'var(--mac-red)' }">{{ saveError }}</span>
        </div>
      </template>
    </div>

    <!-- Intro path · Last touchpoint · Next step — click any to edit -->
    <div class="grid grid-cols-1 gap-3.5 sm:grid-cols-3">
      <div
        v-for="tile in [
          { field: 'intro_path', icon: Link2, label: t('research_desk.warm_intro_path'), empty: t('research_desk.not_recorded') },
          { field: 'last_touchpoint', icon: MessageSquare, label: t('research_desk.last_touchpoint'), empty: t('research_desk.not_recorded') },
          { field: 'next_step', icon: CalendarClock, label: t('research_desk.next_step'), empty: t('research_desk.not_set') },
        ]"
        :key="tile.field"
        class="flex flex-col gap-1 p-2.5"
        :class="tile.field === 'next_step' ? 'mac-tile-tint' : 'mac-tile'"
        :style="
          tile.field === 'next_step'
            ? { borderRadius: '10px', '--tint': pipeline?.next_step_overdue ? 'var(--mac-red)' : 'var(--mac-accent)' }
            : { borderRadius: '10px' }
        "
        :data-testid="`pipeline-${tile.field}`"
      >
        <span
          class="mac-t-label flex items-center gap-1.5"
          :class="tile.field === 'next_step' ? '' : 'mac-c-secondary'"
          :style="tile.field === 'next_step' ? { color: 'var(--tint)' } : {}"
        >
          <component :is="tile.icon" class="h-3 w-3" />
          {{ tile.label }}
        </span>

        <template v-if="editingField === tile.field">
          <textarea
            ref="editorRef"
            v-model="draft"
            rows="2"
            class="mac-field mac-t-caption10 w-full resize-none"
            :aria-label="tile.label"
            :disabled="fieldSaving"
            @keydown="onEditorKeydown"
          />
          <label v-if="tile.field === 'next_step'" class="mac-t-caption10 mac-c-secondary flex items-center gap-1.5">
            {{ t("research_desk.next_step_due") }}
            <input
              v-model="draftDue"
              type="date"
              class="mac-field mac-t-caption10"
              :disabled="fieldSaving"
              data-testid="pipeline-next-step-due"
              @keydown="onEditorKeydown"
            />
          </label>
          <span class="flex items-center gap-1.5">
            <button type="button" class="mac-btn mac-btn--mini mac-btn--prominent" :disabled="fieldSaving" @click="saveEdit">
              {{ t("research_desk.save") }}
            </button>
            <button type="button" class="mac-btn mac-btn--mini" :disabled="fieldSaving" @click="cancelEdit">
              {{ t("research_desk.cancel") }}
            </button>
            <span v-if="fieldSaving" class="mac-spinner" />
          </span>
        </template>

        <button
          v-else
          type="button"
          class="mac-t-caption10 line-clamp-2 text-left"
          :class="pipeline?.[tile.field] ? '' : 'mac-c-secondary'"
          :style="tile.field === 'next_step' ? { color: 'var(--tint)', fontWeight: 500 } : { fontWeight: tile.field === 'intro_path' ? 600 : 400 }"
          :title="t('research_desk.click_to_edit')"
          :disabled="!pipeline"
          @click="startEdit(tile.field)"
        >
          {{ pipeline?.[tile.field] || tile.empty }}
        </button>

        <span
          v-if="tile.field === 'next_step' && pipeline?.next_step && pipeline?.next_step_due && editingField !== 'next_step'"
          class="mac-t-caption10 mac-mono"
          :style="{ color: 'var(--tint)', fontWeight: pipeline.next_step_overdue ? 700 : 400 }"
          data-testid="pipeline-due"
        >
          {{
            pipeline.next_step_overdue
              ? t("research_desk.next_step_overdue", { date: pipeline.next_step_due })
              : t("research_desk.next_step_due_on", { date: pipeline.next_step_due })
          }}
        </span>
      </div>
    </div>
  </div>
</template>
