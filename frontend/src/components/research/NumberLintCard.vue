<script setup>
// Web twin of MacNumberLintView (MacBatchEViews.swift): the no-invented-
// numbers check on the company's latest memo. Reads the dedicated
// /memo-number-lint endpoint and says what it found in words that don't
// overstate it (R28): verified / found elsewhere in sources on file /
// derived / not traced, a tinted bar per tier, and the untraced figures
// with their memo section and excerpt. A thin corpus reads "Not checkable:
// no sources on file" — never a percentage.
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

// The honest summary the server computes (memo_fact_check.summarize_fact_check);
// older payloads carry only supported / checked.
const summary = computed(() => {
  const value = lint.value?.summary;
  return value && typeof value === "object" ? value : null;
});

function n(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.round(number) : 0;
}

const TIERS = [
  ["verified", "var(--mac-green)"],
  ["found_elsewhere", "var(--mac-teal)"],
  ["derived", "var(--mac-indigo)"],
  ["company_reported", "var(--mac-blue)"],
  ["registry_only", "var(--mac-orange)"],
  ["not_traced", "var(--mac-red)"],
];

// not_checkable (thin corpus) | error | no_figures | checked | legacy
const state = computed(() => {
  const s = summary.value;
  if (!s) return lint.value?.error ? "error" : "legacy";
  const status = String(s.status || "").toLowerCase();
  if (status === "error" || lint.value?.error) return "error";
  if (s.thin_corpus || status === "not_checkable") return "not_checkable";
  if (!n(s.checked) || status === "no_figures") return "no_figures";
  return "checked";
});

const tiers = computed(() => {
  const s = summary.value;
  if (!s) return [];
  const total = n(s.checked);
  return TIERS.map(([key, color]) => ({ key, color, count: n(s[key]) }))
    .filter((tier) => tier.count > 0)
    .map((tier) => ({
      ...tier,
      pct: total ? (tier.count / total) * 100 : 0,
      label: t(`reports.fact.short.${tier.key}`, { count: tier.count }),
    }));
});

const found = computed(() => {
  const s = summary.value;
  if (!s) return supported.value;
  return n(s.verified) + n(s.found_elsewhere) + n(s.derived) + n(s.company_reported);
});

const notTraced = computed(() => (summary.value ? n(summary.value.not_traced) : unsupported.value));
const registryOnly = computed(() => (summary.value ? n(summary.value.registry_only) : 0));

const headline = computed(() => {
  switch (state.value) {
    case "not_checkable":
      return t("reports.fact.not_checkable");
    case "error":
      return t("reports.fact.error");
    case "no_figures":
      return t("reports.fact.no_figures");
    case "checked":
      return t("reports.fact.card_counts", { found: found.value, checked: n(summary.value?.checked) });
    default:
      return t("research_desk.numbers_supported", { supported: supported.value, checked: checked.value });
  }
});

const headlineColor = computed(() => {
  if (state.value === "checked" || state.value === "legacy") {
    return notTraced.value === 0 ? "var(--mac-green)" : "var(--mac-orange)";
  }
  return "var(--mac-secondary)";
});

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
  <div class="mac-card flex flex-col gap-2 p-2.5" data-testid="number-lint-card">
    <!-- Label("Numbers lint", number.circle) · what it found · show/refresh -->
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
            class="mac-t-caption10 mac-mono text-right"
            :style="{ color: headlineColor }"
            :data-state="state"
            data-testid="number-lint-headline"
          >
            {{ headline }}
          </span>
          <button
            v-if="unsupported > 0 && findings.length"
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
      <!-- The figures by tier: verified, found elsewhere, derived, not traced… -->
      <template v-if="state === 'checked' && tiers.length">
        <div
          class="flex h-1 w-full overflow-hidden rounded-full"
          style="background: color-mix(in srgb, var(--mac-secondary) 15%, transparent)"
          data-testid="number-lint-bar"
        >
          <div
            v-for="tier in tiers"
            :key="tier.key"
            class="h-full transition-all duration-500"
            :style="{ width: `${tier.pct}%`, background: tier.color }"
          />
        </div>
        <div class="flex flex-wrap gap-x-2.5 gap-y-0.5" data-testid="number-lint-tiers">
          <span
            v-for="tier in tiers"
            :key="tier.key"
            class="mac-t-caption10 mac-c-secondary inline-flex items-center gap-1"
            :data-tier="tier.key"
          >
            <span class="mac-dot" :style="{ background: tier.color }" />
            {{ tier.label }}
          </span>
        </div>
      </template>

      <!-- Older payloads: the one coverage bar they can support. -->
      <div
        v-else-if="state === 'legacy' && lint.coverage_pct != null"
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

      <span
        v-if="state === 'not_checkable'"
        class="mac-t-caption10 mac-c-tertiary"
        data-testid="number-lint-thin"
      >
        {{ t("research_desk.numbers_thin_corpus") }}
        <template v-if="registryOnly"> · {{ t("reports.fact.short.registry_only", { count: registryOnly }) }}</template>
      </span>

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
      <span v-else-if="lint.note && state !== 'not_checkable'" class="mac-t-caption10 mac-c-tertiary">{{ lint.note }}</span>
    </template>
  </div>
</template>
