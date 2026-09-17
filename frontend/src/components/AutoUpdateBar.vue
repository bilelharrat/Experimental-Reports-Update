<script setup>
/**
 * The cadence bar for one background job that spends tokens.
 *
 * Every such job offers the same five choices — manual, 6h, 12h, 1 day,
 * 3 days. Manual means the server loop never fires; the page's own
 * refresh button is then the only way to spend.
 */
import { computed, ref } from "vue";
import { Clock } from "lucide-vue-next";
import api from "../api";
import { t, currentLanguage } from "../i18n";

const props = defineProps({
  channelId: { type: String, required: true },
  channel: { type: Object, default: null },
  compact: { type: Boolean, default: false },
});
const emit = defineEmits(["updated", "error"]);

const saving = ref("");

const choices = computed(() => props.channel?.choices || [
  "manual",
  "6h",
  "12h",
  "1d",
  "3d",
]);
const cadence = computed(() => props.channel?.cadence || "");
const label = computed(() => {
  const pair = props.channel?.label;
  if (!pair) return "";
  return pair[currentLanguage.value] || pair.en || "";
});

function choiceLabel(value) {
  return t(`auto_update.cadence_${value}`);
}

const nextLabel = computed(() => {
  if (cadence.value === "manual") return t("auto_update.manual_note");
  const next = props.channel?.next_run_at;
  if (!next) return "";
  const when = new Date(next);
  if (Number.isNaN(when.getTime())) return "";
  return t("auto_update.next_run", { time: when.toLocaleString() });
});

async function choose(value) {
  if (value === cadence.value || saving.value) return;
  saving.value = value;
  try {
    const updated = await api.putAutoUpdate(props.channelId, { cadence: value });
    emit("updated", updated);
  } catch (err) {
    emit("error", err);
  } finally {
    saving.value = "";
  }
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5">
    <div v-if="!compact && label" class="inline-flex items-center gap-1.5">
      <Clock class="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
      <span class="text-caption1 text-ink-muted">{{ label }}</span>
    </div>
    <div
      class="segmented"
      role="radiogroup"
      :aria-label="label || t('auto_update.title')"
    >
      <button
        v-for="value in choices"
        :key="value"
        type="button"
        role="radio"
        class="segmented-item focus-ring"
        :aria-checked="value === cadence"
        :disabled="Boolean(saving)"
        :title="value === 'manual' ? t('auto_update.manual_note') : ''"
        @click="choose(value)"
      >
        {{ choiceLabel(value) }}
      </button>
    </div>
    <p v-if="nextLabel" class="text-caption1 text-ink-muted">{{ nextLabel }}</p>
  </div>
</template>
