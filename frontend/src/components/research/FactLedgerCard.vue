<script setup>
// The curated fact ledger: dated headline facts that every memo run reads
// before its analysis passes, so a fact the web may or may not surface on
// a given day is on file every time. Edits here write
// data/research/<company>/fact_ledger.md — the same file the pipeline
// injects (see claude_runner.load_memo_fact_ledger).
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";
import { BookOpen, RotateCw } from "lucide-vue-next";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
});

const ledger = ref(null);
const draft = ref("");
const loading = ref(false);
const saving = ref(false);
const savedAt = ref(0);
const error = ref("");

const maxChars = computed(() => ledger.value?.max_chars ?? 6000);
const dirty = computed(() => ledger.value != null && draft.value !== (ledger.value.text || ""));
const overLimit = computed(() => draft.value.length > maxChars.value);
const updatedLabel = computed(() => {
  const iso = ledger.value?.updated_at;
  if (!iso) return "";
  return t("research_desk.fact_ledger_updated", { date: String(iso).slice(0, 10) });
});

async function load() {
  if (!props.companyId) return;
  loading.value = true;
  error.value = "";
  try {
    ledger.value = await api.getFactLedger(props.companyId);
    draft.value = ledger.value?.text || "";
  } catch {
    ledger.value = null;
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (!props.companyId || saving.value || overLimit.value) return;
  saving.value = true;
  error.value = "";
  try {
    ledger.value = await api.putFactLedger(props.companyId, draft.value);
    draft.value = ledger.value?.text || "";
    savedAt.value = Date.now();
  } catch {
    error.value = t("research_desk.fact_ledger_error");
  } finally {
    saving.value = false;
  }
}

watch(() => props.companyId, load, { immediate: true });
</script>

<template>
  <div class="mac-card flex flex-col gap-2 p-2.5">
    <div class="flex items-center gap-2">
      <BookOpen class="mac-c-accent h-3.5 w-3.5" stroke-width="2.4" />
      <span class="mac-t-subheadline font-semibold" style="font-weight: 600">
        {{ t("research_desk.fact_ledger_title") }}
      </span>
      <span class="flex-1" />
      <span v-if="ledger && !ledger.exists && !dirty" class="mac-t-caption10 mac-c-secondary">
        {{ t("research_desk.fact_ledger_none") }}
      </span>
      <span v-else-if="updatedLabel && !dirty" class="mac-t-caption10 mac-c-secondary">
        {{ updatedLabel }}
      </span>
      <span
        v-if="savedAt && !dirty"
        class="mac-t-caption10"
        style="color: var(--mac-green)"
        data-testid="ledger-saved"
      >
        {{ t("research_desk.fact_ledger_saved") }}
      </span>
      <button
        type="button"
        class="mac-btn mac-btn--mini"
        :disabled="!dirty || saving || overLimit"
        data-testid="ledger-save"
        @click="save"
      >
        {{ t("research_desk.fact_ledger_save") }}
      </button>
      <button
        type="button"
        class="mac-btn mac-btn--mini mac-btn--plain"
        :title="t('research_desk.refresh')"
        :disabled="loading"
        @click="load"
      >
        <RotateCw class="h-3 w-3" :class="{ 'animate-spin': loading }" />
      </button>
    </div>

    <span class="mac-t-caption10 mac-c-tertiary">{{ t("research_desk.fact_ledger_hint") }}</span>

    <textarea
      v-model="draft"
      class="mac-field mac-mono w-full resize-y rounded-md p-2 text-[11px] leading-relaxed"
      rows="7"
      spellcheck="false"
      :placeholder="t('research_desk.fact_ledger_placeholder')"
      data-testid="ledger-text"
    />

    <div class="flex items-center gap-2">
      <span
        class="mac-t-caption10 mac-mono"
        :style="{ color: overLimit ? 'var(--mac-red)' : 'var(--mac-secondary)' }"
        data-testid="ledger-count"
      >
        {{ t("research_desk.fact_ledger_chars", { count: draft.length, max: maxChars }) }}
      </span>
      <span class="flex-1" />
      <span v-if="error" class="mac-t-caption10" style="color: var(--mac-red)">{{ error }}</span>
    </div>
  </div>
</template>
