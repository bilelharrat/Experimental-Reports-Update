<script setup>
// Web twin of MacVCRatiosBlotterView.swift: the four ratio metric tiles with
// benchmark badges, the typed-inputs grid (empty by default — a calculator
// over figures you type, nothing fetched or estimated), and the verdict
// readout with the magic-number pill.
import { ref, computed, watch } from "vue";
import { useT } from "../../i18n.js";
import { Gauge, Check, Copy, BadgeCheck, CheckCircle2, AlertTriangle, Crosshair } from "lucide-vue-next";

const t = useT();

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

// Inputs start empty, like the Mac blotter.
const arr = ref(null);
const netNewArr = ref(null);
const netBurn = ref(null);
const arrGrowthRate = ref(null);
const fcfMargin = ref(null);
const ndr = ref(null);
const cacPaybackMonths = ref(null);
const smSpend = ref(null);
const copiedToClipboard = ref(false);
let copiedTimer = null;

watch(
  () => props.companyId,
  () => {
    arr.value = null;
    netNewArr.value = null;
    netBurn.value = null;
    arrGrowthRate.value = null;
    fcfMargin.value = null;
    ndr.value = null;
    cacPaybackMonths.value = null;
    smSpend.value = null;
  },
);

function num(v) {
  return v == null || v === "" || Number.isNaN(Number(v)) ? null : Number(v);
}

const burnMultiple = computed(() => {
  const burn = num(netBurn.value);
  const nn = num(netNewArr.value);
  if (burn == null || nn == null || nn <= 0) return null;
  return burn / nn;
});

const ruleOf40 = computed(() => {
  const g = num(arrGrowthRate.value);
  const f = num(fcfMargin.value);
  if (g == null || f == null) return null;
  return g + f;
});

const magicNumber = computed(() => {
  const nn = num(netNewArr.value);
  const sm = num(smSpend.value);
  if (nn == null || sm == null || sm <= 0) return null;
  return nn / sm;
});

const hasAnyMetric = computed(
  () =>
    burnMultiple.value != null ||
    ruleOf40.value != null ||
    num(ndr.value) != null ||
    num(cacPaybackMonths.value) != null ||
    magicNumber.value != null,
);

const isTopTier = computed(
  () => burnMultiple.value != null && ruleOf40.value != null && burnMultiple.value < 1.0 && ruleOf40.value >= 40,
);

const readoutIsPositive = computed(() => burnMultiple.value != null && burnMultiple.value <= 1.5);

function burnMultipleBadge(value) {
  if (value < 1.0) return { text: t("research_desk.vc_exceptional"), tint: "var(--mac-green)" };
  if (value <= 1.5) return { text: t("research_desk.vc_good"), tint: "var(--mac-blue)" };
  if (value <= 2.0) return { text: t("research_desk.vc_manageable"), tint: "var(--mac-orange)" };
  return { text: t("research_desk.vc_high_burn"), tint: "var(--mac-red)" };
}

const metricTiles = computed(() => {
  const growth = num(arrGrowthRate.value);
  const fcf = num(fcfMargin.value);
  const retention = num(ndr.value);
  const payback = num(cacPaybackMonths.value);
  return [
    {
      title: t("research_desk.vc_burn_multiple"),
      value: burnMultiple.value != null ? `${burnMultiple.value.toFixed(2)}x` : null,
      badge: burnMultiple.value != null ? burnMultipleBadge(burnMultiple.value) : null,
      caption: t("research_desk.vc_burn_caption"),
      target: t("research_desk.vc_burn_target"),
    },
    {
      title: t("research_desk.vc_rule_of_40"),
      value: ruleOf40.value != null ? `${ruleOf40.value.toFixed(1)}%` : null,
      badge:
        ruleOf40.value != null
          ? {
              text: ruleOf40.value >= 40 ? t("research_desk.vc_elite") : t("research_desk.vc_below_40"),
              tint: ruleOf40.value >= 40 ? "var(--mac-green)" : "var(--mac-orange)",
            }
          : null,
      caption: t("research_desk.vc_rule_caption", {
        growth: growth != null ? `${growth.toFixed(0)}%` : "—",
        fcf: fcf != null ? `${fcf.toFixed(0)}%` : "—",
      }),
      target: t("research_desk.vc_rule_target"),
    },
    {
      title: t("research_desk.vc_net_retention"),
      value: retention != null ? `${retention.toFixed(0)}%` : null,
      badge:
        retention != null
          ? {
              text:
                retention >= 130
                  ? t("research_desk.vc_best_in_class")
                  : retention >= 115
                    ? t("research_desk.vc_strong")
                    : t("research_desk.vc_churn_risk"),
              tint:
                retention >= 130 ? "var(--mac-purple)" : retention >= 115 ? "var(--mac-green)" : "var(--mac-red)",
            }
          : null,
      caption: t("research_desk.vc_ndr_caption"),
      target: t("research_desk.vc_ndr_target"),
    },
    {
      title: t("research_desk.vc_cac_payback"),
      value: payback != null ? `${payback.toFixed(1)} mo` : null,
      badge:
        payback != null
          ? {
              text: payback <= 12 ? t("research_desk.vc_efficient") : t("research_desk.vc_slow_payback"),
              tint: payback <= 12 ? "var(--mac-green)" : "var(--mac-orange)",
            }
          : null,
      caption: t("research_desk.vc_cac_caption"),
      target: t("research_desk.vc_cac_target"),
    },
  ];
});

const missingForVerdict = computed(() => {
  const missing = [];
  if (ruleOf40.value == null) missing.push(t("research_desk.vc_rule_of_40"));
  if (num(ndr.value) == null) missing.push(t("research_desk.vc_missing_retention"));
  return missing;
});

const verdictTitle = computed(() => {
  if (burnMultiple.value == null) return "";
  if (isTopTier.value) return t("research_desk.vc_verdict_top");
  if (missingForVerdict.value.length) {
    return t("research_desk.vc_verdict_partial", { missing: missingForVerdict.value.join(" and ") });
  }
  if (burnMultiple.value <= 1.5) return t("research_desk.vc_verdict_strong");
  return t("research_desk.vc_verdict_capital_intensive");
});

const verdictDescription = computed(() => {
  if (burnMultiple.value == null) return "";
  const retention =
    num(ndr.value) != null
      ? t("research_desk.vc_with_retention", { pct: num(ndr.value).toFixed(0) })
      : t("research_desk.vc_retention_not_entered");
  return t("research_desk.vc_verdict_desc", {
    burn: `${burnMultiple.value.toFixed(2)}x`,
    retention,
  });
});

const inputFields = [
  { key: "arr", label: "Current ARR", unit: "$M", model: arr },
  { key: "netNewArr", label: "Net new ARR (TTM)", unit: "$M", model: netNewArr },
  { key: "netBurn", label: "Annual net burn", unit: "$M", model: netBurn },
  { key: "smSpend", label: "S&M spend (TTM)", unit: "$M", model: smSpend },
  { key: "arrGrowthRate", label: "ARR growth (YoY)", unit: "%", model: arrGrowthRate },
  { key: "fcfMargin", label: "FCF margin", unit: "%", model: fcfMargin },
  { key: "ndr", label: "Net dollar retention", unit: "%", model: ndr },
  { key: "cacPaybackMonths", label: "CAC payback", unit: "months", model: cacPaybackMonths },
];

function copyRatiosSummary() {
  const money = (v) => (num(v) != null ? `$${num(v).toFixed(1)}M` : "not entered");
  const pct = (v) => (num(v) != null ? `${num(v).toFixed(0)}%` : "not entered");
  const lines = [
    "--- INSTITUTIONAL VC RATIOS SUMMARY ---",
    `Company: ${props.company?.name || props.companyId}`,
    `ARR: ${money(arr.value)}`,
    `Net New ARR: ${money(netNewArr.value)}`,
    `Annual Net Burn: ${money(netBurn.value)}`,
    `S&M Spend: ${money(smSpend.value)}`,
    `ARR Growth: ${pct(arrGrowthRate.value)}`,
    `FCF Margin: ${pct(fcfMargin.value)}`,
    `Burn Multiple: ${burnMultiple.value != null ? `${burnMultiple.value.toFixed(2)}x (${burnMultipleBadge(burnMultiple.value).text})` : "not entered"}`,
    `Rule of 40: ${ruleOf40.value != null ? `${ruleOf40.value.toFixed(1)}%` : "not entered"}`,
    `Net Dollar Retention (NDR): ${pct(ndr.value)}`,
    `CAC Payback: ${num(cacPaybackMonths.value) != null ? `${num(cacPaybackMonths.value).toFixed(1)} months` : "not entered"}`,
    `Magic Number: ${magicNumber.value != null ? `${magicNumber.value.toFixed(2)}x` : "not entered"}`,
    "---------------------------------------",
  ];
  navigator.clipboard?.writeText(lines.join("\n"));
  copiedToClipboard.value = true;
  if (copiedTimer) clearTimeout(copiedTimer);
  copiedTimer = setTimeout(() => {
    copiedToClipboard.value = false;
  }, 2000);
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-[18px]">
    <!-- MacCardHeader("VC ratios", …, gauge.with.needle) + copy -->
    <div class="mac-cardheader">
      <span class="mac-cardheader-icon"><Gauge class="h-[13px] w-[13px]" stroke-width="2.4" /></span>
      <div class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-headline">{{ t("research_desk.vc_title") }}</span>
        <span class="mac-t-caption mac-c-secondary">{{ t("research_desk.vc_subtitle") }}</span>
      </div>
      <span class="min-w-2 flex-1" />
      <button
        type="button"
        class="mac-btn mac-btn--sm"
        :disabled="!hasAnyMetric"
        @click="copyRatiosSummary"
      >
        <component :is="copiedToClipboard ? Check : Copy" class="h-3 w-3" />
        <span>{{ copiedToClipboard ? t("research_desk.cap_copied") : t("research_desk.vc_copy_ratios") }}</span>
      </button>
    </div>

    <!-- Ratio metric tiles -->
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div
        v-for="tile in metricTiles"
        :key="tile.title"
        class="mac-tile flex flex-col gap-1.5 p-3"
        style="border-radius: 10px"
      >
        <div class="flex items-center gap-2">
          <span class="mac-t-label mac-c-secondary truncate">{{ tile.title }}</span>
          <span class="flex-1" />
          <span v-if="tile.value && tile.badge" class="mac-status-pill" :style="{ '--tint': tile.badge.tint }">
            {{ tile.badge.text }}
          </span>
        </div>
        <span class="mac-t-metric" :class="tile.value == null ? 'mac-c-secondary' : ''">
          {{ tile.value || "—" }}
        </span>
        <span class="mac-t-caption10 mac-c-secondary truncate">{{ tile.caption }}</span>
        <div class="mac-divider" />
        <span class="flex items-center gap-1.5">
          <Crosshair class="mac-c-secondary h-2.5 w-2.5 shrink-0" />
          <span class="mac-t-caption10 mac-c-secondary font-medium">{{ tile.target }}</span>
        </span>
      </div>
    </div>

    <!-- Typed inputs -->
    <div class="mac-tile flex flex-col gap-3 p-3" style="border-radius: 10px">
      <div class="flex items-center">
        <span class="mac-t-label mac-c-secondary">{{ t("research_desk.vc_inputs") }}</span>
        <span class="flex-1" />
        <span class="mac-t-caption mac-mono mac-c-tertiary">{{ t("research_desk.vc_inputs_hint") }}</span>
      </div>

      <div class="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <div v-for="field in inputFields" :key="field.key" class="flex flex-col gap-1">
          <span class="mac-t-caption10 mac-c-secondary truncate">{{ field.label }}</span>
          <div class="flex items-center gap-1">
            <input
              v-model.number="field.model.value"
              type="number"
              placeholder="—"
              class="mac-field mac-mono w-full min-w-0 text-[10px]"
              style="padding: 3px 6px; background: var(--mac-card); box-shadow: var(--mac-btn-edge); border-radius: 6px"
            />
            <span class="mac-t-caption10 mac-c-tertiary shrink-0">{{ field.unit }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Verdict readout -->
    <div
      v-if="burnMultiple != null"
      class="mac-tile-tint flex items-center gap-3 p-3"
      :style="{ borderRadius: '10px', '--tint': isTopTier || readoutIsPositive ? 'var(--mac-green)' : 'var(--mac-orange)' }"
    >
      <component
        :is="isTopTier ? BadgeCheck : readoutIsPositive ? CheckCircle2 : AlertTriangle"
        class="h-[17px] w-[17px] shrink-0"
        :style="{ color: isTopTier || readoutIsPositive ? 'var(--mac-green)' : 'var(--mac-orange)' }"
      />
      <span class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-caption10 font-bold">{{ verdictTitle }}</span>
        <span class="mac-t-caption10 mac-c-secondary">{{ verdictDescription }}</span>
      </span>
      <span class="flex-1" />
      <span
        v-if="magicNumber != null"
        class="flex shrink-0 items-center gap-1.5 rounded-full px-2 py-1"
        :style="{ background: `color-mix(in srgb, ${magicNumber >= 1 ? 'var(--mac-green)' : 'var(--mac-secondary)'} 14%, transparent)` }"
      >
        <span class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.vc_magic_number") }}:</span>
        <span
          class="mac-t-caption10 mac-mono font-bold"
          :style="magicNumber >= 1 ? { color: 'var(--mac-green)' } : {}"
        >
          {{ magicNumber.toFixed(2) }}x
        </span>
        <span
          class="mac-t-caption"
          :style="{ color: magicNumber >= 1 ? 'var(--mac-green)' : 'var(--mac-secondary)' }"
        >
          {{ magicNumber >= 1 ? t("research_desk.vc_expand_sm") : t("research_desk.vc_tune_efficiency") }}
        </span>
      </span>
    </div>
    <p v-else class="mac-t-caption mac-c-secondary">
      {{ t("research_desk.vc_empty_hint") }}
    </p>
  </div>
</template>
