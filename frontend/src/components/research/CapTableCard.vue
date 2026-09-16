<script setup>
import { ref, computed } from "vue";
import { useT } from "../../i18n.js";
import { PieChart, Calculator, TrendingUp } from "lucide-vue-next";
import { formatCompactNumber } from "../../formatters.js";

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

// Simulator State
const checkSizeMillions = ref(15.0);
const preMoneyMillions = ref(60.0);
const optionPoolPercent = ref(10.0);
const futureDilutionPercent = ref(20.0);

const postMoneyMillions = computed(() => {
  return preMoneyMillions.value + checkSizeMillions.value;
});

const initialOwnershipPercent = computed(() => {
  if (postMoneyMillions.value <= 0) return 0;
  return (checkSizeMillions.value / postMoneyMillions.value) * 100.0;
});

const foundersPreMoneyDilutionPercent = computed(() => {
  return Math.max(0, 100.0 - initialOwnershipPercent.value - optionPoolPercent.value);
});

const finalDilutedOwnershipPercent = computed(() => {
  const retention = (100.0 - futureDilutionPercent.value) / 100.0;
  return initialOwnershipPercent.value * retention;
});

const exitScenarios = [250, 500, 1000, 2500, 5000, 10000];

function calculateExitReturn(exitValMillions) {
  const ownership = finalDilutedOwnershipPercent.value / 100.0;
  const exitProceeds = exitValMillions * ownership;
  const moic = checkSizeMillions.value > 0 ? exitProceeds / checkSizeMillions.value : 0;
  return {
    exitVal: exitValMillions,
    proceeds: exitProceeds,
    moic,
  };
}

const lineage = computed(() => {
  return props.company?.cap_table_lineage || props.company?.cap_table || [];
});
</script>

<template>
  <div class="space-y-6">
    <!-- Existing Cap Table Lineage if present -->
    <div v-if="lineage.length" class="rounded-xl border border-border/40 bg-card/60 p-5 backdrop-blur-md">
      <div class="mb-4 border-b border-border/40 pb-3">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-foreground">
          <PieChart class="h-4 w-4 text-primary" />
          {{ t("research_desk.cap_table_lineage") }}
        </h3>
        <p class="text-xs text-muted-foreground">
          {{ t("research_desk.cap_table_subtitle") }}
        </p>
      </div>

      <div class="space-y-3">
        <div
          v-for="holder in lineage"
          :key="holder.name || holder.investor"
          class="flex flex-col gap-1 rounded-lg border border-border/30 bg-background/30 p-2.5 text-xs"
        >
          <div class="flex items-center justify-between">
            <span class="font-medium text-foreground">{{ holder.name || holder.investor }}</span>
            <span class="font-mono font-semibold text-foreground">
              {{ holder.ownership ?? holder.percentage ?? holder.percent }}%
            </span>
          </div>
          <div class="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              class="h-full bg-primary"
              :style="{ width: `${holder.ownership ?? holder.percentage ?? holder.percent ?? 0}%` }"
            />
          </div>
          <div v-if="holder.round || holder.shares" class="flex items-center justify-between text-[10px] text-muted-foreground">
            <span>{{ holder.round || "Common" }}</span>
            <span v-if="holder.shares">{{ holder.shares }} {{ t("research_desk.shares") }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Simulator -->
    <div class="rounded-xl border border-border/40 bg-card/60 p-5 backdrop-blur-md">
      <div class="mb-4 border-b border-border/40 pb-3">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Calculator class="h-4 w-4 text-primary" />
          {{ t("research_desk.dilution_simulator") }}
        </h3>
        <p class="text-xs text-muted-foreground">
          {{ t("research_desk.dilution_subtitle") }}
        </p>
      </div>

      <!-- Input Sliders Grid -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <!-- Check Size -->
        <div>
          <label class="mb-1 flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>{{ t("research_desk.check_size") }}</span>
            <span class="font-mono font-bold text-foreground">${{ checkSizeMillions }}M</span>
          </label>
          <input
            v-model.number="checkSizeMillions"
            type="range"
            min="1"
            max="100"
            step="1"
            class="w-full accent-primary"
          />
        </div>

        <!-- Pre-Money Valuation -->
        <div>
          <label class="mb-1 flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>{{ t("research_desk.pre_money") }}</span>
            <span class="font-mono font-bold text-foreground">${{ preMoneyMillions }}M</span>
          </label>
          <input
            v-model.number="preMoneyMillions"
            type="range"
            min="5"
            max="500"
            step="5"
            class="w-full accent-primary"
          />
        </div>

        <!-- Option Pool -->
        <div>
          <label class="mb-1 flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>{{ t("research_desk.option_pool") }}</span>
            <span class="font-mono font-bold text-foreground">{{ optionPoolPercent }}%</span>
          </label>
          <input
            v-model.number="optionPoolPercent"
            type="range"
            min="0"
            max="25"
            step="1"
            class="w-full accent-primary"
          />
        </div>

        <!-- Future Dilution -->
        <div>
          <label class="mb-1 flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>{{ t("research_desk.future_dilution") }}</span>
            <span class="font-mono font-bold text-foreground">{{ futureDilutionPercent }}%</span>
          </label>
          <input
            v-model.number="futureDilutionPercent"
            type="range"
            min="0"
            max="50"
            step="2"
            class="w-full accent-primary"
          />
        </div>
      </div>

      <!-- Computed Metrics Summary Tiles -->
      <div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="rounded-lg border border-border/40 bg-background/50 p-3">
          <div class="text-[10px] uppercase font-semibold text-muted-foreground">{{ t("research_desk.post_money") }}</div>
          <div class="mt-1 text-lg font-mono font-bold text-foreground">
            ${{ postMoneyMillions.toFixed(1) }}M
          </div>
          <div class="text-[10px] text-muted-foreground">{{ t("research_desk.implied_valuation") }}</div>
        </div>

        <div class="rounded-lg border border-border/40 bg-background/50 p-3">
          <div class="text-[10px] uppercase font-semibold text-muted-foreground">{{ t("research_desk.initial_stake") }}</div>
          <div class="mt-1 text-lg font-mono font-bold text-primary">
            {{ initialOwnershipPercent.toFixed(1) }}%
          </div>
          <div class="text-[10px] text-muted-foreground">{{ t("research_desk.round_ownership") }}</div>
        </div>

        <div class="rounded-lg border border-border/40 bg-background/50 p-3">
          <div class="text-[10px] uppercase font-semibold text-muted-foreground">{{ t("research_desk.founder_team") }}</div>
          <div class="mt-1 text-lg font-mono font-bold text-foreground">
            {{ foundersPreMoneyDilutionPercent.toFixed(1) }}%
          </div>
          <div class="text-[10px] text-muted-foreground">{{ t("research_desk.post_round_retained") }}</div>
        </div>

        <div class="rounded-lg border border-border/40 bg-background/50 p-3">
          <div class="text-[10px] uppercase font-semibold text-muted-foreground">{{ t("research_desk.exit_ownership") }}</div>
          <div class="mt-1 text-lg font-mono font-bold text-emerald-400">
            {{ finalDilutedOwnershipPercent.toFixed(1) }}%
          </div>
          <div class="text-[10px] text-muted-foreground">{{ t("research_desk.after_dilution", { pct: futureDilutionPercent }) }}</div>
        </div>
      </div>

      <!-- Exit Return Matrix -->
      <div class="mt-6">
        <div class="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <TrendingUp class="h-3.5 w-3.5 text-primary" />
          <span>{{ t("research_desk.exit_return_scenarios") }}</span>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead>
              <tr class="border-b border-border/40 text-[11px] font-semibold text-muted-foreground">
                <th class="py-2">{{ t("research_desk.exit_valuation") }}</th>
                <th class="py-2">{{ t("research_desk.gross_proceeds") }}</th>
                <th class="py-2 text-right">{{ t("research_desk.fund_moic") }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border/20 font-mono">
              <tr
                v-for="s in exitScenarios.map(calculateExitReturn)"
                :key="s.exitVal"
                class="hover:bg-muted/30"
              >
                <td class="py-2 font-medium text-foreground">
                  ${{ s.exitVal >= 1000 ? `${(s.exitVal / 1000).toFixed(1)}B` : `${s.exitVal}M` }}
                </td>
                <td class="py-2 text-foreground">
                  ${{ s.proceeds >= 1000 ? `${(s.proceeds / 1000).toFixed(2)}B` : `${s.proceeds.toFixed(1)}M` }}
                </td>
                <td
                  class="py-2 text-right font-bold"
                  :class="s.moic >= 10 ? 'text-emerald-400' : s.moic >= 3 ? 'text-sky-400' : 'text-muted-foreground'"
                >
                  {{ s.moic.toFixed(1) }}x
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
