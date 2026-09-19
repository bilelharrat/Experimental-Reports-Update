<script setup>
// Web twin of MacNumberLintView (MacBatchEViews.swift): the no-invented-
// numbers lint. Reads the dedicated /memo-number-lint endpoint, shows
// "N of M figures found in sources", a tinted coverage bar, and the
// unsupported findings with their memo section and excerpt.
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";
import { Hash, RotateCw } from "lucide-vue-next";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
});

const lint = ref(null);
const loading = ref(false);
const expanded = ref(false);

const hasMemo = computed(() => lint.value?.memo_package != null);
const supported = computed(() => lint.value?.supported ?? 0);
const checked = computed(() => lint.value?.checked ?? 0);
const unsupported = computed(() => lint.value?.unsupported ?? 0);
const findings = computed(() => lint.value?.findings ?? []);

async function loadLint() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    lint.value = await api.getMemoNumberLint(props.companyId);
  } catch {
    lint.value = null;
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.companyId,
  () => {
    expanded.value = false;
    loadLint();
  },
  { immediate: true },
);
</script>

<template>
  <div class="mac-card flex flex-col gap-2 p-2.5">
    <!-- Label("Numbers lint", number.circle) · count · show/refresh -->
    <div class="flex items-center gap-2">
      <Hash class="mac-c-accent h-3.5 w-3.5" stroke-width="2.4" />
      <span class="mac-t-subheadline font-semibold" style="font-weight: 600">
        {{ t("research_desk.numbers_lint_title") }}
      </span>
      <span class="flex-1" />
      <template v-if="lint">
        <span v-if="!hasMemo" class="mac-t-caption10 mac-c-secondary">
          {{ t("research_desk.no_memo_yet") }}
        </span>
        <template v-else>
          <span
            class="mac-t-caption10 mac-mono"
            :style="{ color: unsupported === 0 ? 'var(--mac-green)' : 'var(--mac-orange)' }"
          >
            {{ t("research_desk.numbers_supported", { supported, checked }) }}
          </span>
          <button
            v-if="unsupported > 0"
            type="button"
            class="mac-btn mac-btn--mini"
            @click="expanded = !expanded"
          >
            {{ expanded ? t("research_desk.lint_hide") : t("research_desk.lint_show", { count: unsupported }) }}
          </button>
        </template>
      </template>
      <button
        type="button"
        class="mac-btn mac-btn--mini mac-btn--plain"
        :title="t('research_desk.refresh')"
        :disabled="loading"
        @click="loadLint"
      >
        <RotateCw class="h-3 w-3" :class="{ 'animate-spin': loading }" />
      </button>
    </div>

    <template v-if="lint && hasMemo">
      <!-- Coverage bar -->
      <div
        v-if="lint.coverage_pct != null"
        class="h-1 w-full overflow-hidden rounded-full"
        style="background: color-mix(in srgb, var(--mac-secondary) 15%, transparent)"
      >
        <div
          class="h-full rounded-full transition-all duration-500"
          :style="{
            width: `${lint.coverage_pct}%`,
            background: unsupported === 0 ? 'var(--mac-green)' : 'var(--mac-orange)',
          }"
        />
      </div>

      <template v-if="expanded">
        <div
          v-for="(f, idx) in findings"
          :key="idx"
          class="flex flex-col gap-0.5 rounded-md p-1.5"
          style="background: color-mix(in srgb, var(--mac-orange) 7%, transparent)"
        >
          <span class="flex items-center gap-1.5">
            <span class="mac-t-caption10 mac-mono font-bold" :style="{ color: 'var(--mac-orange)' }">
              {{ f.number }}
            </span>
            <span v-if="f.section" class="mac-t-caption10 mac-c-secondary">§ {{ f.section }}</span>
          </span>
          <span class="mac-t-caption10 mac-c-secondary line-clamp-2">{{ f.excerpt }}</span>
        </div>
        <span v-if="lint.sources?.length" class="mac-t-caption10 mac-c-tertiary">
          {{ t("research_desk.lint_checked_against", { sources: lint.sources.join(" · ") }) }}
        </span>
      </template>
      <span v-else-if="lint.note" class="mac-t-caption10 mac-c-tertiary">{{ lint.note }}</span>
    </template>
  </div>
</template>
