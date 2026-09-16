<script setup>
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false,
  },
  initialFile: {
    type: Object,
    default: null,
  },
  companies: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["close", "filed"]);

const file = ref(null);
const attachTo = ref("");
const companyName = ref("");
const filing = ref(false);
const error = ref(null);
const result = ref(null);

watch(
  () => props.initialFile,
  (newFile) => {
    if (newFile) {
      file.value = newFile;
      const baseName = newFile.name.replace(/\.[^/.]+$/, "");
      companyName.value = baseName.replace(/[_-]/g, " ");
      result.value = null;
      error.value = null;
    }
  },
  { immediate: true },
);

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      if (props.initialFile) {
        file.value = props.initialFile;
        const baseName = props.initialFile.name.replace(/\.[^/.]+$/, "");
        companyName.value = baseName.replace(/[_-]/g, " ");
      }
      result.value = null;
      error.value = null;
    }
  },
);

const canFile = computed(() => {
  if (filing.value || !file.value) return false;
  if (attachTo.value) return true;
  return companyName.value.trim().length > 0;
});

function onFileInput(e) {
  const chosen = e.target.files?.[0];
  if (chosen) {
    file.value = chosen;
    const baseName = chosen.name.replace(/\.[^/.]+$/, "");
    companyName.value = baseName.replace(/[_-]/g, " ");
    result.value = null;
    error.value = null;
  }
}

async function handleFileAndExtract() {
  if (!canFile.value) return;
  filing.value = true;
  error.value = null;

  try {
    const payload = {
      file: file.value,
      companyId: attachTo.value || undefined,
      companyName: !attachTo.value ? companyName.value.trim() : undefined,
    };
    const res = await api.intakeDeck(payload);
    result.value = res;
    emit("filed", res);
  } catch (err) {
    error.value = err?.message || "Failed to file and extract deck";
  } finally {
    filing.value = false;
  }
}

function handleClose() {
  emit("close");
}

function fitToneClass(fit) {
  if (!fit) return "text-muted-foreground";
  if (fit.fit === "strong") return "text-emerald-500";
  if (fit.fit === "partial") return "text-amber-500";
  return "text-rose-500";
}
</script>

<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4"
    role="dialog"
    aria-modal="true"
  >
    <!-- Scrim backdrop -->
    <div
      class="fixed inset-0 bg-black/40 backdrop-blur-sm transition-opacity"
      @click="handleClose"
    />

    <!-- Sheet Panel -->
    <div
      class="relative w-full max-w-lg overflow-hidden rounded-2xl border border-border/60 bg-surface/95 dark:bg-[#1c1c1e]/95 shadow-2xl backdrop-blur-2xl transition-all"
    >
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-border/40 px-5 py-3.5 bg-muted/20">
        <div class="flex items-center gap-2.5">
          <svg
            class="h-5 w-5 text-accent"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="12" y1="18" x2="12" y2="12" />
            <line x1="9" y1="15" x2="12" y2="12" />
            <line x1="15" y1="15" x2="12" y2="12" />
          </svg>
          <span class="font-semibold text-foreground text-sm">
            {{ result ? t("research_desk.intake_results_title") : t("research_desk.intake_title") }}
          </span>
        </div>
        <button
          type="button"
          class="rounded px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors"
          @click="handleClose"
        >
          {{ result ? t("workspace.close") : t("research_desk.cancel") }}
        </button>
      </div>

      <!-- Form Body (Pre-extraction) -->
      <div v-if="!result" class="p-5 space-y-4 text-xs">
        <!-- Selected File Preview -->
        <div class="flex items-center gap-3 rounded-xl border border-border/40 bg-muted/20 p-3">
          <svg class="h-8 w-8 text-rose-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          <div class="min-w-0 flex-1">
            <p class="truncate font-medium text-foreground">
              {{ file ? file.name : t("research_desk.drop_deck_instruction") }}
            </p>
            <p class="text-[11px] text-muted-foreground">
              {{ file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB · PDF / PPTX` : t("research_desk.browse_files") }}
            </p>
          </div>
          <label class="cursor-pointer rounded px-2.5 py-1 text-xs font-medium border border-border/40 bg-surface hover:bg-muted/30 text-foreground transition-colors">
            {{ t("research_desk.browse_files") }}
            <input type="file" accept=".pdf,.pptx" class="hidden" @change="onFileInput" />
          </label>
        </div>

        <!-- Attach To Dropdown -->
        <div class="space-y-1.5">
          <label class="block font-medium text-muted-foreground">
            {{ t("research_desk.intake_company_label") }}
          </label>
          <select
            v-model="attachTo"
            :disabled="filing"
            class="w-full rounded-lg border border-border/60 bg-surface dark:bg-muted/30 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
          >
            <option value="">{{ t("research_desk.intake_new_company") }}</option>
            <option v-for="c in companies" :key="c.id" :value="c.id">
              {{ c.name || c.title }}
            </option>
          </select>
        </div>

        <!-- Company Name if New Record -->
        <div v-if="!attachTo" class="space-y-1.5">
          <label class="block font-medium text-muted-foreground">
            {{ t("research_desk.intake_name_placeholder") }}
          </label>
          <input
            v-model="companyName"
            type="text"
            :disabled="filing"
            :placeholder="t('research_desk.intake_name_placeholder')"
            class="w-full rounded-lg border border-border/60 bg-surface dark:bg-muted/30 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>

        <!-- Info callout -->
        <div class="flex items-start gap-2.5 rounded-lg border border-accent/20 bg-accent/5 p-3 text-[11px] leading-relaxed text-muted-foreground">
          <svg class="h-4 w-4 text-accent shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <p>{{ t("research_desk.intake_info_callout") }}</p>
        </div>

        <!-- Error display -->
        <div v-if="error" class="rounded-lg border border-rose-500/20 bg-rose-500/10 p-2 text-[11px] text-rose-600 dark:text-rose-400">
          {{ error }}
        </div>
      </div>

      <!-- Result Body (Post-extraction) -->
      <div v-else class="max-h-[60vh] overflow-y-auto p-5 space-y-4 text-xs">
        <!-- Result Header -->
        <div class="flex items-center justify-between rounded-xl border border-border/40 bg-muted/20 p-3">
          <div class="flex items-center gap-2.5">
            <svg class="h-5 w-5 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <div>
              <p class="font-semibold text-foreground">{{ result.company?.name || companyName }}</p>
              <p class="text-[11px] text-muted-foreground">
                {{ result.file_name }} · {{ t("research_desk.intake_slides_count", { count: result.slide_count || 0 }) }}
              </p>
            </div>
          </div>

          <div v-if="result.thesis" class="text-right">
            <p class="font-mono font-bold text-xs" :class="fitToneClass(result.thesis)">
              {{ result.thesis.score != null ? `${result.thesis.score}% fit` : result.thesis.label }}
            </p>
            <p class="text-[10px] text-muted-foreground">{{ result.thesis.label }}</p>
          </div>
        </div>

        <!-- Extracted Fields Table -->
        <div v-if="result.fields && result.fields.length" class="overflow-hidden rounded-xl border border-border/40 bg-surface/50">
          <div
            v-for="(field, idx) in result.fields"
            :key="idx"
            class="flex items-start gap-3 border-b border-border/20 p-2.5 last:border-b-0 hover:bg-muted/10 text-xs"
          >
            <span class="w-24 shrink-0 font-medium text-muted-foreground">{{ field.label }}</span>
            <span class="w-24 shrink-0 font-mono font-semibold text-foreground tabular-nums">{{ field.display }}</span>
            <div class="min-w-0 flex-1">
              <span v-if="field.page" class="mr-1.5 font-semibold text-accent text-[11px]">p. {{ field.page }}</span>
              <span v-if="field.excerpt" class="text-[11px] text-muted-foreground line-clamp-2">{{ field.excerpt }}</span>
            </div>
          </div>
        </div>

        <!-- Open questions list -->
        <div v-if="result.thesis?.open_questions?.length" class="space-y-1.5">
          <p class="font-semibold text-muted-foreground text-[11px] uppercase tracking-wider">
            {{ t("research_desk.intake_open_questions") }}
          </p>
          <ul class="space-y-1 rounded-lg border border-border/30 bg-muted/20 p-2.5">
            <li
              v-for="(q, idx) in result.thesis.open_questions"
              :key="idx"
              class="flex items-start gap-2 text-[11px] text-foreground"
            >
              <span class="text-accent font-bold">•</span>
              <span>{{ q }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between border-t border-border/40 px-5 py-3 bg-muted/20">
        <div v-if="result">
          <button
            type="button"
            class="rounded-lg px-3 py-1.5 text-xs font-medium border border-border/40 bg-surface hover:bg-muted/40 text-foreground transition-colors"
            @click="handleClose"
          >
            {{ t("research_desk.intake_open_pipeline") }}
          </button>
        </div>
        <div v-else />

        <div v-if="!result" class="flex items-center gap-2">
          <button
            type="button"
            class="rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/40 transition-colors"
            @click="handleClose"
          >
            {{ t("research_desk.cancel") }}
          </button>
          <button
            type="button"
            class="btn-filled flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-white transition-all disabled:opacity-50"
            :disabled="!canFile"
            @click="handleFileAndExtract"
          >
            <svg
              v-if="filing"
              class="h-3.5 w-3.5 animate-spin"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="12" y1="2" x2="12" y2="6" />
              <line x1="12" y1="18" x2="12" y2="22" />
              <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
              <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
              <line x1="2" y1="12" x2="6" y2="12" />
              <line x1="18" y1="12" x2="22" y2="12" />
              <line x1="4.93" y1="19.07" x2="7.76" y2="16.24" />
              <line x1="16.24" y1="7.76" x2="19.07" y2="4.93" />
            </svg>
            <span>{{ filing ? t("research_desk.intake_extracting") : t("research_desk.intake_extract_button") }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
