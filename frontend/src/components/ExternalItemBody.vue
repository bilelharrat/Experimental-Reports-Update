<script setup>
import { computed, ref, watch } from "vue";
import { Languages } from "lucide-vue-next";
import { useT } from "../i18n.js";

const props = defineProps({
  item: { type: Object, required: true },
});

const t = useT();

// Tab state: source (item.language) or translation (item.translation.language)
const tab = ref("source");

watch(
  () => props.item?.id,
  () => {
    tab.value = "source";
  },
);

const sourceLang = computed(() => props.item?.language || "en");
const targetLang = computed(() => props.item?.translation?.language || null);
const showTranslationTab = computed(
  () => !!props.item?.translation && targetLang.value && targetLang.value !== sourceLang.value,
);

const view = computed(() => {
  if (tab.value === "translation" && props.item?.translation) {
    return {
      lang: props.item.translation.language,
      title: props.item.translation.title,
      summary: props.item.translation.summary,
      key_points: props.item.translation.key_points || [],
      full_text: props.item.translation.full_text,
    };
  }
  return {
    lang: sourceLang.value,
    title: props.item?.title,
    summary: props.item?.summary,
    key_points: props.item?.key_points || [],
    full_text: null,
  };
});

const langLabel = (code) =>
  code === "en" ? "English" : code === "zh" ? "中文" : code || "?";
</script>

<template>
  <div class="space-y-5">
    <div v-if="showTranslationTab" class="flex items-center gap-1">
      <Languages class="h-3.5 w-3.5 text-ink-muted mr-1" />
      <button
        type="button"
        @click="tab = 'source'"
        :class="[ 'text-xs px-2.5 py-1 rounded-md border focus-ring', tab === 'source' ? 'bg-accent text-white border-accent' : 'bg-surface-muted border-subtle text-ink-secondary hover:border-strong', ]"
      >
        {{ t("external.source_panel") }} · {{ langLabel(sourceLang) }}
      </button>
      <button
        type="button"
        @click="tab = 'translation'"
        :class="[ 'text-xs px-2.5 py-1 rounded-md border focus-ring', tab === 'translation' ? 'bg-accent text-white border-accent' : 'bg-surface-muted border-subtle text-ink-secondary hover:border-strong', ]"
      >
        {{ t("external.translation_panel") }} · {{ langLabel(targetLang) }}
      </button>
    </div>

    <section v-if="view.summary">
      <h3 class="vogue-label mb-2">
        {{ t("external.summary") }}
      </h3>
      <p class="text-ink-secondary leading-relaxed whitespace-pre-wrap">
        {{ view.summary }}
      </p>
    </section>

    <section v-if="view.key_points.length">
      <h3 class="vogue-label mb-2">
        {{ t("external.key_points") }}
      </h3>
      <ul class="space-y-1.5 list-disc pl-5 text-ink-secondary">
        <li v-for="(kp, i) in view.key_points" :key="i">
          {{ kp }}
        </li>
      </ul>
    </section>

    <details v-if="view.full_text" class="text-sm">
      <summary
        class="cursor-pointer vogue-label hover:text-ink-primary"
      >
        {{ t("external.full_translation") }}
      </summary>
      <pre
        class="mt-2 whitespace-pre-wrap font-body text-sm leading-relaxed text-ink-primary bg-surface-muted rounded-lg p-4 border border-subtle"
        >{{ view.full_text }}</pre
      >
    </details>
  </div>
</template>
