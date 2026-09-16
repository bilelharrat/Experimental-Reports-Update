<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useT } from "../../i18n.js";
import { Gauge, CheckCircle2, AlertTriangle, Info } from "lucide-vue-next";

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

// Interactive state
const arr = ref(null);
const netNewArr = ref(null);
const netBurn = ref(null);
const arrGrowthRate = ref(null);
const fcfMargin = ref(null);
const ndr = ref(null);
const cacPaybackMonths = ref(null);
const smSpend = ref(null);

function initializeFromCompany() {
  const m = props.company?.metrics || {};
  if (m.arr != null) arr.value = Number((m.arr / 1_000_000).toFixed(1));
  else if (m.annual_recurring_revenue != null) arr.value = Number((m.annual_recurring_revenue / 1_000_000).toFixed(1));
  else arr.value = 18.5;

  netNewArr.value = m.net_new_arr ? Number((m.net_new_arr / 1_000_000).toFixed(1)) : 8.0;
  netBurn.value = m.net_burn ? Number((m.net_burn / 1_000_000).toFixed(1)) : 6.5;
  arrGrowthRate.value = m.arr_growth_rate ?? m.growth_rate ?? 65;
  fcfMargin.value = m.fcf_margin ?? -12;
  ndr.value = m.ndr ?? 128;
  cacPaybackMonths.value = m.cac_payback_months ?? 14;
  smSpend.value = m.sm_spend ? Number((m.sm_spend / 1_000_000).toFixed(1)) : 7.2;
}

watch(() => props.company, initializeFromCompany, { immediate: true });
onMounted(initializeFromCompany);

// Computed VC Ratios
const burnMultiple = computed(() => {
  if (netBurn.value == null || netNewArr.value == null || netNewArr.value <= 0) return null;
  return netBurn.value / netNewArr.value;
});

const burnMultipleClass = computed(() => {
  if (burnMultiple.value == null) return "text-muted-foreground";
  if (burnMultiple.value < 1.0) return "text-emerald-400";
  if (burnMultiple.value < 1.5) return "text-sky-400";
  if (burnMultiple.value < 2.0) return "text-amber-400";
  return "text-rose-400";
});

const burnMultipleRating = computed(() => {
  if (burnMultiple.value == null) return "";
  if (burnMultiple.value < 1.0) return t("research_desk.efficiency_great");
  if (burnMultiple.value < 1.5) return t("research_desk.efficiency_good");
  if (burnMultiple.value < 2.0) return t("research_desk.efficiency_fair");
  return t("research_desk.efficiency_poor");
});

const ruleOf40 = computed(() => {
  if (arrGrowthRate.value == null || fcfMargin.value == null) return null;
  return arrGrowthRate.value + fcfMargin.value;
});

const ruleOf40Class = computed(() => {
  if (ruleOf40.value == null) return "text-muted-foreground";
  if (ruleOf40.value >= 40) return "text-emerald-400";
  if (ruleOf40.value >= 20) return "text-sky-400";
  return "text-amber-400";
});

const ruleOf40Rating = computed(() => {
  if (ruleOf40.value == null) return "";
  if (ruleOf40.value >= 40) return t("research_desk.top_tier");
  if (ruleOf40.value >= 20) return t("research_desk.moderate_tier");
  return t("research_desk.subpar_tier");
});

const magicNumber = computed(() => {
  if (netNewArr.value == null || smSpend.value == null || smSpend.value <= 0) return null;
  return netNewArr.value / smSpend.value;
});

const magicNumberClass = computed(() => {
  if (magicNumber.value == null) return "text-muted-foreground";
  if (magicNumber.value >= 1.0) return "text-emerald-400";
  if (magicNumber.value >= 0.75) return "text-sky-400";
  return "text-amber-400";
});

const magicNumberRating = computed(() => {
  if (magicNumber.value == null) return "";
  if (magicNumber.value >= 1.0) return t("research_desk.magic_efficient");
  if (magicNumber.value >= 0.75) return t("research_desk.magic_healthy");
  return t("research_desk.magic_poor");
});

const isTopTier = computed(() => {
  return burnMultiple.value != null && burnMultiple.value < 1.0 && ruleOf40.value != null && ruleOf40.value >= 40;
});
</script>

<template>
  <div class="rounded-xl border border-border/40 bg-card/60 p-5 backdrop-blur-md">
    <!-- Header -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-border/40 pb-3">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Gauge class="h-4 w-4 text-primary" />
          {{ t("research_desk.vc_ratios_title") }}
        </h3>
        <p class="text-xs text-muted-foreground">
          {{ t("research_desk.vc_ratios_subtitle") }}
        </p>
      </div>

      <div
        v-if="isTopTier"
        class="flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-400"
      >
        <CheckCircle2 class="h-3.5 w-3.5" />
        <span>{{ t("research_desk.top_decile_efficiency") }}</span>
      </div>
    </div>

    <!-- Benchmark Cards Grid -->
    <div class="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
      <!-- Burn Multiple -->
      <div class="rounded-lg border border-border/40 bg-background/50 p-3.5">
        <div class="flex items-center justify-between text-xs text-muted-foreground">
          <span>{{ t("research_desk.burn_multiple") }}</span>
          <span class="text-[10px]">{{ t("research_desk.burn_multiple_calc") }}</span>
        </div>
        <div class="mt-2 flex items-baseline gap-2">
          <span
            class="text-2xl font-bold font-mono"
            :class="burnMultipleClass"
          >
            {{ burnMultiple != null ? `${burnMultiple.toFixed(2)}x` : "—" }}
          </span>
          <span class="text-[11px] font-medium text-muted-foreground">
            {{ burnMultipleRating }}
          </span>
        </div>
      </div>

      <!-- Rule of 40 -->
      <div class="rounded-lg border border-border/40 bg-background/50 p-3.5">
        <div class="flex items-center justify-between text-xs text-muted-foreground">
          <span>{{ t("research_desk.rule_of_40") }}</span>
          <span class="text-[10px]">{{ t("research_desk.rule_of_40_calc") }}</span>
        </div>
        <div class="mt-2 flex items-baseline gap-2">
          <span
            class="text-2xl font-bold font-mono"
            :class="ruleOf40Class"
          >
            {{ ruleOf40 != null ? `${ruleOf40.toFixed(1)}%` : "—" }}
          </span>
          <span class="text-[11px] font-medium text-muted-foreground">
            {{ ruleOf40Rating }}
          </span>
        </div>
      </div>

      <!-- Magic Number -->
      <div class="rounded-lg border border-border/40 bg-background/50 p-3.5">
        <div class="flex items-center justify-between text-xs text-muted-foreground">
          <span>{{ t("research_desk.magic_number") }}</span>
          <span class="text-[10px]">{{ t("research_desk.magic_number_calc") }}</span>
        </div>
        <div class="mt-2 flex items-baseline gap-2">
          <span
            class="text-2xl font-bold font-mono"
            :class="magicNumberClass"
          >
            {{ magicNumber != null ? `${magicNumber.toFixed(2)}x` : "—" }}
          </span>
          <span class="text-[11px] font-medium text-muted-foreground">
            {{ magicNumberRating }}
          </span>
        </div>
      </div>
    </div>

    <!-- Inputs Tuning Grid -->
    <div class="rounded-lg border border-border/30 bg-background/30 p-4">
      <div class="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {{ t("research_desk.financial_inputs_calc") }}
      </div>

      <div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <label class="mb-1 block text-[11px] text-muted-foreground">{{ t("research_desk.total_arr") }}</label>
          <input
            v-model.number="arr"
            type="number"
            step="0.5"
            class="w-full rounded border border-border/50 bg-background/50 px-2 py-1 text-xs font-mono text-foreground focus:border-primary focus:outline-none"
          />
        </div>

        <div>
          <label class="mb-1 block text-[11px] text-muted-foreground">{{ t("research_desk.net_new_arr") }}</label>
          <input
            v-model.number="netNewArr"
            type="number"
            step="0.5"
            class="w-full rounded border border-border/50 bg-background/50 px-2 py-1 text-xs font-mono text-foreground focus:border-primary focus:outline-none"
          />
        </div>

        <div>
          <label class="mb-1 block text-[11px] text-muted-foreground">{{ t("research_desk.net_annual_burn") }}</label>
          <input
            v-model.number="netBurn"
            type="number"
            step="0.5"
            class="w-full rounded border border-border/50 bg-background/50 px-2 py-1 text-xs font-mono text-foreground focus:border-primary focus:outline-none"
          />
        </div>

        <div>
          <label class="mb-1 block text-[11px] text-muted-foreground">{{ t("research_desk.yoy_arr_growth") }}</label>
          <input
            v-model.number="arrGrowthRate"
            type="number"
            step="5"
            class="w-full rounded border border-border/50 bg-background/50 px-2 py-1 text-xs font-mono text-foreground focus:border-primary focus:outline-none"
          />
        </div>

        <div>
          <label class="mb-1 block text-[11px] text-muted-foreground">{{ t("research_desk.fcf_margin") }}</label>
          <input
            v-model.number="fcfMargin"
            type="number"
            step="2"
            class="w-full rounded border border-border/50 bg-background/50 px-2 py-1 text-xs font-mono text-foreground focus:border-primary focus:outline-none"
          />
        </div>

        <div>
          <label class="mb-1 block text-[11px] text-muted-foreground">{{ t("research_desk.net_dollar_retention") }}</label>
          <input
            v-model.number="ndr"
            type="number"
            step="1"
            class="w-full rounded border border-border/50 bg-background/50 px-2 py-1 text-xs font-mono text-foreground focus:border-primary focus:outline-none"
          />
        </div>

        <div>
          <label class="mb-1 block text-[11px] text-muted-foreground">{{ t("research_desk.cac_payback_mo") }}</label>
          <input
            v-model.number="cacPaybackMonths"
            type="number"
            step="1"
            class="w-full rounded border border-border/50 bg-background/50 px-2 py-1 text-xs font-mono text-foreground focus:border-primary focus:outline-none"
          />
        </div>

        <div>
          <label class="mb-1 block text-[11px] text-muted-foreground">{{ t("research_desk.sm_spend") }}</label>
          <input
            v-model.number="smSpend"
            type="number"
            step="0.5"
            class="w-full rounded border border-border/50 bg-background/50 px-2 py-1 text-xs font-mono text-foreground focus:border-primary focus:outline-none"
          />
        </div>
      </div>
    </div>
  </div>
</template>
