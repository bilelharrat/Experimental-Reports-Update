<script setup>
// Web twin of MacCapTableSimulatorView.swift: round-terms sliders, the
// post-money stat tiles, later-round dilution toggle, the blue/orange/green
// ownership bar with legend, and the exit proceeds & MOIC matrix. Inputs are
// saved to the company record via the cap-model endpoint, like the Mac.
import { ref, computed, watch } from "vue";
import { useT } from "../../i18n.js";
import { PieChart, AlertTriangle, Save, Copy, RotateCcw } from "lucide-vue-next";
import api from "../../api.js";

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

const ROUNDS = ["Seed", "Series A", "Series B", "Series C", "Growth"];

// MacCapTableSimulatorView inputs and defaults
const roundName = ref("Series A");
const checkSizeMillions = ref(15.0);
const preMoneyMillions = ref(60.0);
const optionPoolPercent = ref(10.0);
const modelFutureDilution = ref(true);
const futureDilutionPercent = ref(22.0);
const fundSizeMillions = ref(400.0);
const copiedNotice = ref(false);
const saveState = ref(null);
const savedModelLoaded = ref(false);
const savedModelFailed = ref(false);
let copiedTimer = null;

const postMoneyMillions = computed(() => preMoneyMillions.value + checkSizeMillions.value);

const initialOwnershipPercent = computed(() => {
  if (postMoneyMillions.value <= 0) return 0;
  return (checkSizeMillions.value / postMoneyMillions.value) * 100.0;
});

const foundersPreMoneyDilutionPercent = computed(() =>
  Math.max(0, 100.0 - initialOwnershipPercent.value - optionPoolPercent.value),
);

const isOverAllocated = computed(
  () => initialOwnershipPercent.value + optionPoolPercent.value > 100.0,
);

const finalDilutedOwnershipPercent = computed(() => {
  if (!modelFutureDilution.value) return initialOwnershipPercent.value;
  const retention = (100.0 - futureDilutionPercent.value) / 100.0;
  return initialOwnershipPercent.value * retention;
});

// Standard VC exit horizons (values in $M)
const scenarios = [
  { exit: 250.0, label: "$250M · acquisition" },
  { exit: 500.0, label: "$500M · strategic" },
  { exit: 1000.0, label: "$1.0B · unicorn" },
  { exit: 3000.0, label: "$3.0B · public scale" },
  { exit: 5000.0, label: "$5.0B · decacorn" },
  { exit: 10000.0, label: "$10B · mega exit" },
];

function scenarioRow(sc) {
  const proceeds = sc.exit * (finalDilutedOwnershipPercent.value / 100.0);
  const moic = checkSizeMillions.value > 0 ? proceeds / checkSizeMillions.value : 0;
  const fundReturnPct = fundSizeMillions.value > 0 ? (proceeds / fundSizeMillions.value) * 100.0 : 0;
  return { proceeds, moic, fundReturnPct, isFundReturner: fundReturnPct >= 100.0 };
}

function resetToStandardSeriesA() {
  roundName.value = "Series A";
  checkSizeMillions.value = 15.0;
  preMoneyMillions.value = 60.0;
  optionPoolPercent.value = 10.0;
  modelFutureDilution.value = true;
  futureDilutionPercent.value = 22.0;
}

async function loadSaved() {
  savedModelLoaded.value = false;
  savedModelFailed.value = false;
  try {
    const model = await api.getCapModel(props.companyId);
    const inputs = model?.inputs || model || {};
    if (inputs.pre_money_musd != null) preMoneyMillions.value = inputs.pre_money_musd;
    const check = inputs.our_check_musd ?? inputs.new_money_musd;
    if (check != null) checkSizeMillions.value = check;
    if (inputs.option_pool_pct_post != null) optionPoolPercent.value = inputs.option_pool_pct_post;
    if (inputs.notes) roundName.value = inputs.notes;
  } catch {
    savedModelFailed.value = true;
  } finally {
    savedModelLoaded.value = true;
  }
}

watch(
  () => props.companyId,
  () => {
    saveState.value = null;
    copiedNotice.value = false;
    resetToStandardSeriesA();
    loadSaved();
  },
  { immediate: true },
);

async function saveModel() {
  saveState.value = t("research_desk.cap_saving");
  try {
    await api.saveCapModel(props.companyId, {
      pre_money_musd: preMoneyMillions.value,
      new_money_musd: checkSizeMillions.value,
      our_check_musd: checkSizeMillions.value,
      option_pool_pct_post: optionPoolPercent.value,
      liquidation_preference_x: 1.0,
      participating: false,
      exit_values_musd: scenarios.map((s) => s.exit),
      notes: roundName.value,
    });
    saveState.value = t("research_desk.cap_saved_to", { name: props.company?.name || props.companyId });
  } catch {
    saveState.value = t("research_desk.cap_save_failed");
  }
}

function copyTermSheetSummary() {
  const fmt1 = (v) => v.toFixed(1);
  const lines = [
    `TERM SHEET CAP TABLE SUMMARY — ${props.company?.name || props.companyId}`,
    `Round: ${roundName.value}`,
    `Investment Check Size: $${fmt1(checkSizeMillions.value)}M`,
    `Pre-Money Valuation: $${fmt1(preMoneyMillions.value)}M`,
    `Post-Money Valuation: $${fmt1(postMoneyMillions.value)}M`,
    `Initial Ownership: ${fmt1(initialOwnershipPercent.value)}%`,
    `Unallocated Option Pool: ${fmt1(optionPoolPercent.value)}%`,
    `Modeled Future Dilution: ${futureDilutionPercent.value.toFixed(0)}%`,
    `Diluted Ownership at Exit: ${fmt1(finalDilutedOwnershipPercent.value)}%`,
    "",
    "EXIT SCENARIOS:",
    ...scenarios.map((sc) => {
      const proceeds = (sc.exit * finalDilutedOwnershipPercent.value) / 100.0;
      const moic = checkSizeMillions.value > 0 ? proceeds / checkSizeMillions.value : 0;
      return `- $${sc.exit >= 1000 ? `${(sc.exit / 1000).toFixed(1)}B` : `${sc.exit.toFixed(0)}M`} Exit -> Proceeds: $${fmt1(proceeds)}M (${fmt1(moic)}x MOIC)`;
    }),
  ];
  navigator.clipboard?.writeText(lines.join("\n"));
  copiedNotice.value = true;
  if (copiedTimer) clearTimeout(copiedTimer);
  copiedTimer = setTimeout(() => {
    copiedNotice.value = false;
  }, 2500);
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-[18px]">
    <!-- MacCardHeader("Cap table & waterfall", …, chart.pie) + save/copy/reset -->
    <div class="mac-cardheader flex-wrap">
      <span class="mac-cardheader-icon"><PieChart class="h-[13px] w-[13px]" stroke-width="2.4" /></span>
      <div class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-headline">{{ t("research_desk.cap_title") }}</span>
        <span class="mac-t-caption mac-c-secondary">{{ t("research_desk.cap_subtitle") }}</span>
      </div>
      <span class="min-w-2 flex-1" />
      <span v-if="!savedModelLoaded" class="mac-spinner" />
      <template v-else-if="savedModelFailed">
        <span class="mac-t-caption flex items-center gap-1" :style="{ color: 'var(--mac-orange)' }">
          <AlertTriangle class="h-3 w-3" />
          {{ t("research_desk.cap_saved_unavailable") }}
        </span>
        <button type="button" class="mac-btn mac-btn--sm" @click="loadSaved">
          {{ t("research_desk.retry") }}
        </button>
      </template>
      <span v-else-if="saveState" class="mac-t-caption mac-c-secondary">{{ saveState }}</span>
      <span v-if="copiedNotice" class="mac-t-caption" :style="{ color: 'var(--mac-green)' }">
        {{ t("research_desk.cap_copied") }}
      </span>
      <button
        type="button"
        class="mac-btn mac-btn--sm"
        :disabled="!savedModelLoaded || savedModelFailed"
        :title="t('research_desk.cap_save_help')"
        @click="saveModel"
      >
        <Save class="h-3 w-3" />
        <span>{{ t("research_desk.cap_save") }}</span>
      </button>
      <button type="button" class="mac-btn mac-btn--sm" @click="copyTermSheetSummary">
        <Copy class="h-3 w-3" />
        <span>{{ t("research_desk.cap_copy_term_sheet") }}</span>
      </button>
      <button
        type="button"
        class="mac-btn mac-btn--sm"
        :title="t('research_desk.cap_reset_help')"
        @click="resetToStandardSeriesA"
      >
        <RotateCcw class="h-3 w-3" />
      </button>
    </div>

    <!-- Round inputs: two columns -->
    <div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <!-- Round terms -->
      <div class="flex flex-col gap-3.5">
        <span class="mac-t-label mac-c-secondary">{{ t("research_desk.cap_round_terms") }}</span>

        <div class="flex items-center gap-3">
          <span class="mac-t-caption10 shrink-0">{{ t("research_desk.cap_round") }}</span>
          <div class="mac-segmented flex-1">
            <button
              v-for="r in ROUNDS"
              :key="r"
              type="button"
              class="mac-segment"
              :class="{ 'is-selected': roundName === r }"
              @click="roundName = r"
            >
              {{ r }}
            </button>
          </div>
        </div>

        <div class="flex flex-col gap-1">
          <div class="flex items-center">
            <span class="mac-t-caption10">{{ t("research_desk.cap_our_check") }}</span>
            <span class="flex-1" />
            <span class="mac-t-caption10 mac-mono font-bold">${{ checkSizeMillions.toFixed(1) }}M</span>
          </div>
          <input v-model.number="checkSizeMillions" type="range" min="1" max="80" step="0.5" />
        </div>

        <div class="flex flex-col gap-1">
          <div class="flex items-center">
            <span class="mac-t-caption10">{{ t("research_desk.cap_pre_money") }}</span>
            <span class="flex-1" />
            <span class="mac-t-caption10 mac-mono font-bold">${{ preMoneyMillions.toFixed(1) }}M</span>
          </div>
          <input v-model.number="preMoneyMillions" type="range" min="5" max="400" step="2.5" />
        </div>

        <div class="flex flex-col gap-1">
          <div class="flex items-center">
            <span class="mac-t-caption10">{{ t("research_desk.cap_option_pool") }}</span>
            <span class="flex-1" />
            <span class="mac-t-caption10 mac-mono font-bold">{{ optionPoolPercent.toFixed(1) }}%</span>
          </div>
          <input v-model.number="optionPoolPercent" type="range" min="0" max="25" step="1" />
        </div>
      </div>

      <!-- Post-money & dilution -->
      <div class="flex flex-col gap-3.5">
        <span class="mac-t-label mac-c-secondary">{{ t("research_desk.cap_post_money_dilution") }}</span>

        <div class="grid grid-cols-3 gap-3">
          <div class="mac-stattile is-compact">
            <span class="mac-t-label mac-c-secondary truncate">{{ t("research_desk.cap_post_money") }}</span>
            <span class="mac-t-metric-sm truncate">${{ postMoneyMillions.toFixed(1) }}M</span>
            <span class="mac-t-caption mac-c-tertiary truncate">{{ t("research_desk.cap_post_money_detail") }}</span>
          </div>
          <div class="mac-stattile is-compact">
            <span class="mac-t-label mac-c-secondary truncate">{{ t("research_desk.cap_ownership_close") }}</span>
            <span class="mac-t-metric-sm truncate">{{ initialOwnershipPercent.toFixed(1) }}%</span>
            <span class="mac-t-caption mac-c-tertiary truncate">{{ t("research_desk.cap_ownership_close_detail") }}</span>
          </div>
          <div class="mac-stattile is-compact">
            <span class="mac-t-label mac-c-secondary truncate">{{ t("research_desk.cap_ownership_exit") }}</span>
            <span class="mac-t-metric-sm truncate">{{ finalDilutedOwnershipPercent.toFixed(1) }}%</span>
            <span class="mac-t-caption mac-c-tertiary truncate">
              {{
                modelFutureDilution
                  ? t("research_desk.cap_after_dilution", { pct: futureDilutionPercent.toFixed(0) })
                  : t("research_desk.cap_no_later_rounds")
              }}
            </span>
          </div>
        </div>

        <div class="mac-tile flex flex-col gap-1.5 p-2">
          <label class="flex items-center gap-2">
            <input v-model="modelFutureDilution" type="checkbox" />
            <span class="mac-t-caption10" style="font-weight: 500">{{ t("research_desk.cap_model_dilution") }}</span>
          </label>

          <template v-if="modelFutureDilution">
            <div class="flex items-center">
              <span class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.cap_cumulative_dilution") }}</span>
              <span class="flex-1" />
              <span class="mac-t-caption10 mac-mono font-bold">{{ futureDilutionPercent.toFixed(0) }}%</span>
            </div>
            <input v-model.number="futureDilutionPercent" type="range" min="5" max="50" step="1" />
          </template>
        </div>

        <div class="flex items-center">
          <span class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.cap_fund_size") }}</span>
          <span class="flex-1" />
          <span class="mac-t-caption10 mac-mono font-semibold">${{ fundSizeMillions.toFixed(0) }}M</span>
        </div>
      </div>
    </div>

    <!-- Post-round ownership bar -->
    <div class="flex flex-col gap-1.5">
      <div class="flex items-center">
        <span class="mac-t-label mac-c-secondary">{{ t("research_desk.cap_post_round_ownership") }}</span>
        <span class="flex-1" />
        <span v-if="!isOverAllocated" class="mac-t-caption mac-mono mac-c-tertiary">
          {{ t("research_desk.cap_sums_to_100") }}
        </span>
      </div>

      <div class="flex h-3.5 w-full gap-[2px] overflow-hidden rounded">
        <div
          :style="{ background: 'var(--mac-blue)', width: `${(foundersPreMoneyDilutionPercent / Math.max(0.0001, foundersPreMoneyDilutionPercent + optionPoolPercent + initialOwnershipPercent)) * 100}%` }"
          :title="`Founders & Prior Investors: ${foundersPreMoneyDilutionPercent.toFixed(1)}%`"
        />
        <div
          :style="{ background: 'var(--mac-orange)', width: `${(optionPoolPercent / Math.max(0.0001, foundersPreMoneyDilutionPercent + optionPoolPercent + initialOwnershipPercent)) * 100}%` }"
          :title="`Unallocated Option Pool: ${optionPoolPercent.toFixed(1)}%`"
        />
        <div
          :style="{ background: 'var(--mac-green)', width: `${(initialOwnershipPercent / Math.max(0.0001, foundersPreMoneyDilutionPercent + optionPoolPercent + initialOwnershipPercent)) * 100}%` }"
          :title="`Our Fund (${roundName}): ${initialOwnershipPercent.toFixed(1)}%`"
        />
      </div>

      <div v-if="isOverAllocated" class="flex items-center gap-1.5">
        <AlertTriangle class="h-3.5 w-3.5" :style="{ color: 'var(--mac-orange)' }" />
        <span class="mac-t-caption" :style="{ color: 'var(--mac-orange)' }">
          {{ t("research_desk.cap_over_allocated") }}
        </span>
      </div>

      <div class="flex flex-wrap items-center gap-4">
        <span class="flex items-center gap-[5px]">
          <span class="h-[7px] w-[7px] rounded-full" :style="{ background: 'var(--mac-blue)' }" />
          <span class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.cap_legend_founders") }}</span>
          <span class="mac-t-caption10 mac-mono font-semibold">{{ foundersPreMoneyDilutionPercent.toFixed(1) }}%</span>
        </span>
        <span class="flex items-center gap-[5px]">
          <span class="h-[7px] w-[7px] rounded-full" :style="{ background: 'var(--mac-orange)' }" />
          <span class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.cap_legend_pool") }}</span>
          <span class="mac-t-caption10 mac-mono font-semibold">{{ optionPoolPercent.toFixed(1) }}%</span>
        </span>
        <span class="flex items-center gap-[5px]">
          <span class="h-[7px] w-[7px] rounded-full" :style="{ background: 'var(--mac-green)' }" />
          <span class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.cap_legend_ours") }} · {{ roundName }}</span>
          <span class="mac-t-caption10 mac-mono font-semibold">{{ initialOwnershipPercent.toFixed(1) }}%</span>
        </span>
      </div>
    </div>

    <!-- Exit proceeds & MOIC matrix -->
    <div class="flex flex-col gap-2">
      <div class="flex items-center">
        <span class="mac-t-label mac-c-secondary">{{ t("research_desk.cap_exit_matrix") }}</span>
        <span class="flex-1" />
        <span class="mac-t-caption mac-mono mac-c-tertiary">
          {{ t("research_desk.cap_at_ownership", { pct: finalDilutedOwnershipPercent.toFixed(1) }) }}
        </span>
      </div>

      <div class="mac-scroll overflow-x-auto">
        <div class="min-w-[640px]">
          <div class="mac-t-label mac-c-secondary flex items-center gap-2.5 px-2.5 py-1.5">
            <span class="w-[170px] shrink-0">{{ t("research_desk.cap_col_exit") }}</span>
            <span class="w-[130px] shrink-0 text-right">{{ t("research_desk.cap_col_stake") }}</span>
            <span class="w-[130px] shrink-0 text-right">{{ t("research_desk.cap_col_proceeds") }}</span>
            <span class="w-[90px] shrink-0 text-right">MOIC</span>
            <span class="flex-1 text-right">{{ t("research_desk.cap_col_fund_returned") }}</span>
          </div>

          <div class="flex flex-col gap-1">
            <div
              v-for="sc in scenarios"
              :key="sc.exit"
              class="flex items-center gap-2.5 rounded-md px-2.5 py-1.5"
              :style="scenarioRow(sc).isFundReturner ? { background: 'color-mix(in srgb, var(--mac-green) 5%, transparent)' } : {}"
            >
              <span class="mac-t-caption10 w-[170px] shrink-0 font-medium">{{ sc.label }}</span>
              <span class="mac-t-caption10 mac-mono mac-c-secondary w-[130px] shrink-0 text-right">
                {{ finalDilutedOwnershipPercent.toFixed(1) }}%
              </span>
              <span
                class="mac-t-caption10 mac-mono w-[130px] shrink-0 text-right font-bold"
                :style="scenarioRow(sc).moic >= 10 ? { color: 'var(--mac-green)' } : {}"
              >
                ${{ scenarioRow(sc).proceeds.toFixed(1) }}M
              </span>
              <span
                class="mac-t-caption10 mac-mono w-[90px] shrink-0 text-right font-bold"
                :style="
                  scenarioRow(sc).moic >= 10
                    ? { color: 'var(--mac-green)' }
                    : scenarioRow(sc).moic >= 3
                      ? { color: 'var(--mac-accent)' }
                      : {}
                "
              >
                {{ scenarioRow(sc).moic.toFixed(1) }}x
              </span>
              <span class="flex flex-1 items-center justify-end gap-1">
                <span
                  class="mac-t-caption10 mac-mono"
                  :style="{
                    color: scenarioRow(sc).isFundReturner ? 'var(--mac-green)' : 'var(--mac-secondary)',
                    fontWeight: scenarioRow(sc).isFundReturner ? 900 : 600,
                  }"
                >
                  {{ scenarioRow(sc).fundReturnPct.toFixed(1) }}%
                </span>
                <span
                  v-if="scenarioRow(sc).isFundReturner"
                  class="mac-status-pill"
                  :style="{ '--tint': 'var(--mac-green)' }"
                >
                  {{ t("research_desk.cap_returns_fund") }}
                </span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
