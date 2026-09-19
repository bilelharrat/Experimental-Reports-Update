<script setup>
// Web twin of MacPitchDeckIntakeSheet (MacPitchDeckDropZone.swift): a 520pt
// sheet with bar-material header/footer. Form: the deck tile, "Attach to"
// picker, company-name field and the info callout. Result: extracted fields
// with page references, thesis fit, open questions, and the Open on
// Pipeline / Summarize with Claude actions.
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import api from "../../api.js";
import { t } from "../../i18n.js";
import {
  FileUp,
  FileText,
  Info,
  BadgeCheck,
  PlusCircle,
  Sparkles,
  Layers,
} from "lucide-vue-next";

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false,
  },
  initialFile: {
    type: Object,
    default: null,
  },
  companyId: {
    type: String,
    default: "",
  },
  companies: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["close", "intake-complete"]);

const router = useRouter();

const file = ref(null);
const attachTo = ref("");
const companyName = ref("");
const filing = ref(false);
const error = ref(null);
const result = ref(null);

function seedFromFile(nextFile) {
  file.value = nextFile;
  const baseName = String(nextFile?.name || "").replace(/\.[^/.]+$/, "");
  companyName.value = baseName.replace(/[_-]/g, " ");
}

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      if (props.initialFile) seedFromFile(props.initialFile);
      attachTo.value = "";
      result.value = null;
      error.value = null;
    }
  },
);

watch(
  () => props.initialFile,
  (newFile) => {
    if (newFile) {
      seedFromFile(newFile);
      result.value = null;
      error.value = null;
    }
  },
  { immediate: true },
);

const canFile = computed(() => {
  if (filing.value || !file.value) return false;
  if (attachTo.value) return true;
  return companyName.value.trim().length > 0;
});

const resultFields = computed(() => result.value?.extraction?.fields ?? result.value?.fields ?? []);
const resultFileId = computed(() => result.value?.file?.id ?? null);
const resultFileName = computed(() => result.value?.file?.filename ?? result.value?.file_name ?? "Deck");

// MacIntakeField.label / .display
function fieldLabel(field) {
  if (field.name === "post_money") return "Post-money";
  if (field.name === "arr") return "ARR";
  return String(field.name || "field").replace(/^./, (c) => c.toUpperCase());
}

function fieldDisplay(field) {
  const usd = field.usd;
  if (usd != null) {
    if (usd >= 1e9) return `$${(usd / 1e9).toFixed(2)}B`;
    if (usd >= 1e6) return `$${(usd / 1e6).toFixed(1)}M`;
    if (usd >= 1e3) return `$${(usd / 1e3).toFixed(0)}K`;
  }
  if (field.name === "runway") return `${field.value} months`;
  return field.value;
}

function fitTint(fit) {
  if (fit?.fit === "strong") return "var(--mac-green)";
  if (fit?.fit === "partial") return "var(--mac-orange)";
  if (fit?.fit === "weak" || fit?.fit === "disqualified") return "var(--mac-red)";
  return "var(--mac-secondary)";
}

function onFileInput(e) {
  const chosen = e.target.files?.[0];
  if (chosen) {
    seedFromFile(chosen);
    result.value = null;
    error.value = null;
  }
}

async function handleFileAndExtract() {
  if (!canFile.value) return;
  filing.value = true;
  error.value = null;

  try {
    const res = await api.intakeDeck({
      file: file.value,
      companyId: attachTo.value || undefined,
      companyName: !attachTo.value ? companyName.value.trim() : undefined,
    });
    result.value = res;
    emit("intake-complete", res);
  } catch (err) {
    error.value = err?.message || t("research_desk.intake_failed");
  } finally {
    filing.value = false;
  }
}

function openOnPipeline() {
  const cid = result.value?.company?.id;
  emit("close");
  if (cid) router.push({ name: "research-desk-company", params: { companyId: cid } });
}

async function summarizeWithClaude() {
  const cid = result.value?.company?.id;
  const fid = resultFileId.value;
  if (!cid || !fid) return;
  try {
    await api.generateResearchFileSummary(cid, fid);
  } catch {
    // the jobs rail shows the truth
  }
  emit("close");
}
</script>

<template>
  <div
    v-if="isOpen"
    class="mac-desk fixed inset-0 z-50 flex items-center justify-center p-4"
    style="background: transparent"
    role="dialog"
    aria-modal="true"
  >
    <!-- Sheet scrim -->
    <div class="fixed inset-0" style="background: rgba(0, 0, 0, 0.28)" @click="emit('close')" />

    <!-- Sheet -->
    <div
      class="relative flex max-h-[85vh] w-full max-w-[520px] flex-col overflow-hidden rounded-[12px]"
      style="background: var(--mac-canvas); box-shadow: 0 0 0 1px var(--mac-hairline), 0 24px 60px rgba(0, 0, 0, 0.35)"
    >
      <!-- Header on bar material -->
      <div class="mac-bar-material flex items-center gap-2 px-5 py-3.5">
        <FileUp class="mac-c-accent h-[17px] w-[17px]" stroke-width="2.2" />
        <span class="mac-t-headline-sys">
          {{ result ? t("research_desk.intake_results_title") : t("research_desk.intake_title") }}
        </span>
        <span class="flex-1" />
        <button type="button" class="mac-btn mac-btn--sm" @click="emit('close')">
          {{ result ? t("workspace.close") : t("research_desk.cancel") }}
        </button>
      </div>
      <div class="mac-divider" />

      <!-- Form body -->
      <div v-if="!result" class="mac-scroll flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5">
        <!-- Deck tile -->
        <div
          class="flex items-center gap-3 rounded-lg p-3"
          style="background: color-mix(in srgb, var(--mac-secondary) 6%, transparent)"
        >
          <FileText class="h-7 w-7 shrink-0" :style="{ color: 'var(--mac-red)' }" stroke-width="1.8" />
          <span class="flex min-w-0 flex-1 flex-col gap-0.5">
            <span class="mac-t-subheadline truncate font-semibold">
              {{ file ? file.name : t("research_desk.drop_deck_instruction") }}
            </span>
            <span class="mac-t-caption10 mac-c-secondary truncate">
              {{
                file
                  ? `${(file.name.split(".").pop() || "").toUpperCase()} · ${t("research_desk.intake_uploads_note")}`
                  : ""
              }}
            </span>
          </span>
          <label class="mac-btn mac-btn--sm shrink-0">
            {{ t("research_desk.browse_files") }}
            <input type="file" accept=".pdf,.pptx" class="hidden" @change="onFileInput" />
          </label>
        </div>

        <!-- Attach to -->
        <div class="flex flex-col gap-1.5">
          <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.intake_company_label") }}</span>
          <div class="mac-popup">
            <select v-model="attachTo" :disabled="filing" class="w-full">
              <option value="">{{ t("research_desk.intake_new_company") }}</option>
              <option v-for="c in companies" :key="c.id" :value="c.id">
                {{ c.name || c.title || c.id }}
              </option>
            </select>
          </div>
        </div>

        <!-- Company name when new -->
        <div v-if="!attachTo" class="flex flex-col gap-1.5">
          <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.intake_company_name_label") }}</span>
          <input
            v-model="companyName"
            type="text"
            :disabled="filing"
            :placeholder="t('research_desk.intake_name_placeholder')"
            class="mac-field w-full"
            @keydown.enter.prevent="handleFileAndExtract"
          />
        </div>

        <!-- Info callout -->
        <div
          class="flex items-start gap-2.5 rounded-md p-2.5"
          style="background: color-mix(in srgb, var(--mac-accent) 6%, transparent)"
        >
          <Info class="mac-c-secondary mt-px h-3.5 w-3.5 shrink-0" />
          <p class="mac-t-caption10 mac-c-secondary" style="line-height: 1.45">
            {{ t("research_desk.intake_info_callout") }}
          </p>
        </div>

        <span v-if="error" class="mac-t-caption10" :style="{ color: 'var(--mac-red)' }">{{ error }}</span>
      </div>

      <!-- Result body -->
      <div v-else class="mac-scroll flex min-h-0 flex-1 flex-col gap-3.5 overflow-y-auto p-5">
        <div class="flex items-center gap-2.5">
          <BadgeCheck class="h-[17px] w-[17px] shrink-0" :style="{ color: 'var(--mac-green)' }" />
          <span class="flex min-w-0 flex-1 flex-col gap-0.5">
            <span class="mac-t-subheadline truncate font-semibold">
              {{ result.company?.name || result.company?.id || companyName }}
            </span>
            <span class="mac-t-caption10 mac-c-secondary truncate">
              {{ resultFileName }} · {{ t("research_desk.intake_slides_count", { count: result.slide_count || 0 }) }}
            </span>
          </span>
          <span
            v-if="result.thesis"
            class="flex shrink-0 flex-col items-end gap-0.5"
            :title="(result.thesis.reasons || []).join('\n')"
          >
            <span class="mac-t-caption10 mac-mono font-bold" :style="{ color: fitTint(result.thesis) }">
              {{
                result.thesis.score != null
                  ? t("research_desk.intake_fit", { score: result.thesis.score })
                  : result.thesis.label
              }}
            </span>
            <span class="mac-t-caption10 mac-c-secondary">{{ result.thesis.label }}</span>
          </span>
        </div>

        <!-- Extracted fields -->
        <p v-if="resultFields.length === 0" class="mac-t-caption10 mac-c-secondary" style="line-height: 1.45">
          {{ t("research_desk.intake_no_fields") }}
        </p>
        <div
          v-else
          class="overflow-hidden rounded-lg"
          style="background: color-mix(in srgb, var(--mac-secondary) 5%, transparent)"
        >
          <template v-for="(field, idx) in resultFields" :key="field.name">
            <div class="flex items-start gap-2.5 px-2.5 py-1.5" :class="idx > 0 ? 'mac-hairline-t' : ''">
              <span class="mac-t-caption10 w-[90px] shrink-0 font-semibold">{{ fieldLabel(field) }}</span>
              <span class="mac-t-caption10 mac-mono w-[90px] shrink-0 font-medium">{{ fieldDisplay(field) }}</span>
              <span class="flex min-w-0 flex-col gap-px">
                <span v-if="field.page" class="mac-t-caption10 mac-c-accent font-semibold">p. {{ field.page }}</span>
                <span v-if="field.excerpt" class="mac-t-caption10 mac-c-secondary line-clamp-2">{{ field.excerpt }}</span>
              </span>
            </div>
          </template>
        </div>

        <!-- Open questions -->
        <div v-if="result.thesis?.open_questions?.length" class="flex flex-col gap-1">
          <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.intake_open_questions") }}</span>
          <span
            v-for="(q, idx) in result.thesis.open_questions"
            :key="idx"
            class="mac-t-caption10 flex items-start gap-1.5"
          >
            <span class="mac-c-secondary">?</span>
            <span>{{ q }}</span>
          </span>
        </div>
      </div>

      <div class="mac-divider" />

      <!-- Footer on bar material -->
      <div class="mac-bar-material flex items-center gap-2 px-5 py-3">
        <template v-if="result">
          <button type="button" class="mac-btn mac-btn--sm" @click="openOnPipeline">
            <Layers class="h-3 w-3" />
            <span>{{ t("research_desk.intake_open_pipeline") }}</span>
          </button>
          <button
            v-if="resultFileId"
            type="button"
            class="mac-btn mac-btn--sm"
            :title="t('research_desk.intake_summarize_help')"
            @click="summarizeWithClaude"
          >
            <Sparkles class="h-3 w-3" />
            <span>{{ t("research_desk.intake_summarize") }}</span>
          </button>
        </template>
        <span class="flex-1" />
        <button
          v-if="!result"
          type="button"
          class="mac-btn mac-btn--sm mac-btn--prominent"
          :disabled="!canFile"
          @click="handleFileAndExtract"
        >
          <span v-if="filing" class="mac-spinner" style="width: 12px; height: 12px" />
          <PlusCircle v-else class="h-3 w-3" />
          <span>{{ filing ? t("research_desk.intake_extracting") : t("research_desk.intake_extract_button") }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
