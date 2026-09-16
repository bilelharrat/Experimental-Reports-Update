<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useT } from "../../i18n.js";
import {
  GitCommit,
  User,
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

const pipeline = ref({
  stage: "Sourced",
  stages: defaultStages,
  warmth_score: 80,
  deal_lead: "",
  intro_path: "",
  last_touchpoint: "",
  next_step: "",
  days_in_stage: 0,
});

async function loadPipeline() {
  if (!props.companyId) return;
  loading.value = true;
  saveError.value = null;
  try {
    const res = await api.getDealPipeline(props.companyId);
    if (res) {
      pipeline.value = {
        ...pipeline.value,
        ...res,
        stages: res.stages?.length ? res.stages : defaultStages,
      };
    }
  } catch {
    // If not found, use default pipeline state
  } finally {
    loading.value = false;
    loadAttempted.value = true;
  }
}

watch(() => props.companyId, loadPipeline, { immediate: true });
onMounted(loadPipeline);

const warmthPillClass = computed(() => {
  const s = pipeline.value.warmth_score ?? 0;
  if (s >= 80) return "text-emerald-400 bg-emerald-500/15 border-emerald-500/20";
  if (s >= 50) return "text-amber-400 bg-amber-500/15 border-amber-500/20";
  return "text-neutral-400 bg-white/5 border-white/10";
});

function stageIndex(stage) {
  return (pipeline.value.stages || defaultStages).indexOf(stage);
}

async function changeStage(newStage) {
  if (saving.value || pipeline.value.stage === newStage) return;
  const previous = pipeline.value.stage;
  pipeline.value.stage = newStage;
  pipeline.value.days_in_stage = 0;
  saving.value = true;
  saveError.value = null;

  try {
    const payload = {
      stage: newStage,
      deal_lead: pipeline.value.deal_lead,
      intro_path: pipeline.value.intro_path,
      last_touchpoint: pipeline.value.last_touchpoint,
      next_step: pipeline.value.next_step,
    };
    const res = await api.updateDealPipeline(props.companyId, payload);
    if (res) {
      pipeline.value = { ...pipeline.value, ...res };
    }
    emit("stage-updated", newStage);
  } catch (err) {
    pipeline.value.stage = previous;
    saveError.value = err?.message || "Failed to update pipeline stage";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="rounded-xl border border-white/[0.08] bg-[#1c1c1f] p-3.5 shadow-xs transition-all text-white">
    <!-- Header (MacDealPipelineView.swift:15-32) -->
    <div class="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
      <div class="flex items-center gap-2">
        <GitCommit class="h-4 w-4 text-[#0a84ff]" />
        <span class="font-semibold text-white text-xs">
          {{ t("research_desk.deal_pipeline") }}
        </span>
        <span class="text-xs text-neutral-400 hidden sm:inline">
          · {{ t("research_desk.deal_pipeline_subtitle") }}
        </span>
      </div>

      <div class="flex items-center gap-2">
        <span
          v-if="pipeline.warmth_score != null"
          class="rounded-full border px-2 py-0.5 text-[11px] font-mono font-medium"
          :class="warmthPillClass"
        >
          {{ t("research_desk.warmth_label") }} {{ pipeline.warmth_score }}
        </span>

        <span
          v-if="pipeline.deal_lead"
          class="flex items-center gap-1 text-[11px] text-neutral-400"
        >
          <User class="h-3 w-3" />
          {{ pipeline.deal_lead }}
        </span>
      </div>
    </div>

    <!-- Stepper Section (MacDealPipelineView.swift:73-110) -->
    <div class="mt-3.5 space-y-2">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-neutral-400">
          {{ t("research_desk.current_stage") }}
        </span>
        <span v-if="pipeline.days_in_stage != null" class="text-xs font-mono text-neutral-400">
          {{ pipeline.days_in_stage }} {{ t("research_desk.days_in") }} {{ pipeline.stage }}
        </span>
      </div>

      <!-- Equal-width Stage Tiles -->
      <div class="grid grid-cols-2 gap-1.5 sm:grid-cols-5">
        <button
          v-for="(stage, idx) in (pipeline.stages || defaultStages)"
          :key="stage"
          type="button"
          class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-left transition-all border outline-none select-none"
          :class="[
            pipeline.stage === stage
              ? 'bg-blue-500/20 border-blue-500/40 text-blue-400 shadow-2xs font-semibold'
              : stageIndex(stage) < stageIndex(pipeline.stage)
              ? 'bg-emerald-500/10 border-emerald-500/20 text-white font-medium'
              : 'bg-white/[0.04] border-white/[0.04] text-neutral-400 hover:bg-white/[0.06] font-normal',
          ]"
          :disabled="saving"
          @click="changeStage(stage)"
        >
          <!-- 16x16 Stage Indicator Circle -->
          <span
            class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
            :class="[
              pipeline.stage === stage
                ? 'bg-[#0a84ff] text-white'
                : stageIndex(stage) < stageIndex(pipeline.stage)
                ? 'bg-emerald-500 text-white'
                : 'bg-white/10 text-neutral-400',
            ]"
          >
            <Check v-if="stageIndex(stage) < stageIndex(pipeline.stage)" class="h-2.5 w-2.5 stroke-[3]" />
            <span v-else>{{ idx + 1 }}</span>
          </span>

          <span class="truncate text-[11px]">
            {{ stage }}
          </span>
        </button>
      </div>

      <div v-if="saveError" class="flex items-center gap-1.5 text-xs text-rose-400 mt-1">
        <AlertTriangle class="h-3.5 w-3.5" />
        <span>{{ saveError }}</span>
      </div>
    </div>

    <!-- Relationship Pathway & CRM Interactions (3 Tiles side by side, matching MacDealPipelineView:120-165) -->
    <div class="mt-3.5 grid grid-cols-1 gap-2 sm:grid-cols-3">
      <!-- Intro Path Tile -->
      <div class="rounded-lg bg-white/[0.04] border border-white/[0.04] p-2.5 flex flex-col justify-between">
        <div class="flex items-center gap-1.5 text-xs text-neutral-400">
          <Link2 class="h-3.5 w-3.5" />
          <span>{{ t("research_desk.warm_intro_path") }}</span>
        </div>
        <div class="mt-1.5 text-xs font-semibold text-white truncate">
          {{ pipeline.intro_path || "—" }}
        </div>
      </div>

      <!-- Last Touchpoint Tile -->
      <div class="rounded-lg bg-white/[0.04] border border-white/[0.04] p-2.5 flex flex-col justify-between">
        <div class="flex items-center gap-1.5 text-xs text-neutral-400">
          <MessageSquare class="h-3.5 w-3.5" />
          <span>{{ t("research_desk.last_touchpoint") }}</span>
        </div>
        <div class="mt-1.5 text-xs text-neutral-400 truncate">
          {{ pipeline.last_touchpoint || "—" }}
        </div>
      </div>

      <!-- Next Step Tile (tinted accent, matching Swift appleGlassTile(tint: Color.accentColor)) -->
      <div class="rounded-lg bg-blue-500/10 border border-blue-500/20 p-2.5 flex flex-col justify-between">
        <div class="flex items-center gap-1.5 text-xs text-blue-400 font-medium">
          <CalendarClock class="h-3.5 w-3.5" />
          <span>{{ t("research_desk.next_step") }}</span>
        </div>
        <div class="mt-1.5 text-xs font-medium text-blue-400 truncate">
          {{ pipeline.next_step || "—" }}
        </div>
      </div>
    </div>
  </div>
</template>
