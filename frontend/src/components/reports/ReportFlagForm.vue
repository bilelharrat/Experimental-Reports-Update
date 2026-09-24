<script setup>
// Flag a passage of a report (G7): the quoted text, what is wrong with it
// (wrong number / unsupported / unclear / missing / tone) and an optional
// note. The parent posts it with api.addReportComment; this is only the form.
import { computed, ref, watch } from "vue";
import { Flag } from "lucide-vue-next";
import { useT } from "../../i18n.js";

const props = defineProps({
  quote: { type: String, default: "" },
  // The heading the passage sits under, if the document has one.
  sectionLabel: { type: String, default: "" },
  // The language of the document the passage was selected in (en | zh).
  language: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
});

const emit = defineEmits(["submit", "cancel"]);
const t = useT();

const FLAGS = ["wrong_number", "unsupported", "unclear", "missing", "tone"];
const flag = ref("wrong_number");
const note = ref("");

watch(
  () => props.quote,
  () => {
    flag.value = "wrong_number";
    note.value = "";
  },
);

const where = computed(() => {
  const parts = [];
  if (props.sectionLabel) parts.push(props.sectionLabel);
  if (props.language === "en" || props.language === "zh") {
    parts.push(t("comments.in_language", { language: t(`comments.lang.${props.language}`) }));
  }
  return parts.join(" · ");
});

function submit() {
  if (props.busy) return;
  emit("submit", { flag: flag.value, note: note.value.trim() });
}
</script>

<template>
  <form
    class="flex flex-col gap-2 rounded-card border border-warning/30 bg-warning-soft/40 p-3"
    data-testid="flag-form"
    @submit.prevent="submit"
  >
    <div class="flex items-center gap-1.5 text-footnote font-semibold text-ink-primary">
      <Flag class="h-3.5 w-3.5 text-warning-ink" />
      {{ t("comments.flag_title") }}
    </div>
    <blockquote
      class="line-clamp-4 border-l-2 border-warning/60 pl-2 text-footnote italic text-ink-secondary"
      data-testid="flag-quote"
    >
      {{ quote }}
    </blockquote>
    <div v-if="where" class="text-caption1 text-ink-muted" data-testid="flag-where">{{ where }}</div>
    <div
      class="flex flex-wrap gap-1"
      role="radiogroup"
      :aria-label="t('comments.flag_type_label')"
    >
      <button
        v-for="kind in FLAGS"
        :key="kind"
        type="button"
        role="radio"
        class="rounded-full border px-2 py-0.5 text-caption1 font-semibold transition-colors focus-ring"
        :class="
          flag === kind
            ? 'border-warning bg-warning text-white'
            : 'border-subtle bg-surface text-ink-secondary hover:text-ink-primary'
        "
        :aria-checked="flag === kind"
        :data-testid="`flag-type-${kind}`"
        @click="flag = kind"
      >
        {{ t(`comments.flag_type.${kind}`) }}
      </button>
    </div>
    <textarea
      v-model="note"
      rows="2"
      maxlength="4000"
      class="field field-sm w-full resize-y"
      :placeholder="t('comments.flag_note')"
      :aria-label="t('comments.flag_note')"
      data-testid="flag-note"
    ></textarea>
    <p v-if="error" class="text-caption1 text-danger" role="alert">{{ error }}</p>
    <div class="flex items-center justify-end gap-2">
      <button type="button" class="btn-plain btn-sm focus-ring" data-testid="flag-cancel" @click="emit('cancel')">
        {{ t("common.cancel") }}
      </button>
      <button type="submit" class="btn-filled btn-sm focus-ring" :disabled="busy" data-testid="flag-submit">
        {{ t("comments.flag_submit") }}
      </button>
    </div>
  </form>
</template>
