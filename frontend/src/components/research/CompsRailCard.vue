<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useT } from "../../i18n.js";
import { BarChart3, RotateCw, ExternalLink } from "lucide-vue-next";
import { api } from "../../api.js";
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

const loading = ref(false);
const compsData = ref(null);

async function loadComps() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    const res = await api.getCompanyComps(props.companyId);
    compsData.value = res;
  } catch (err) {
    compsData.value = null;
  } finally {
    loading.value = false;
  }
}

watch(() => props.companyId, loadComps, { immediate: true });
onMounted(loadComps);

const peersList = computed(() => {
  if (compsData.value?.peers?.length) {
    return compsData.value.peers;
  }
  if (props.company?.competitor_cards?.length) {
    return props.company.competitor_cards.map((c) => ({
      ticker: c.ticker || c.id || "—",
      name: c.name || c.title || c.id,
      price: c.price != null ? `$${c.price}` : "—",
      marketCap: c.market_cap ? formatCompactNumber(c.market_cap) : (c.valuation || "—"),
      psRatio: c.ps_ratio ? `${Number(c.ps_ratio).toFixed(1)}x` : "—",
      status: c.status || (c.ticker ? "Public" : "Private"),
      notes: c.differentiator || c.description || "",
    }));
  }
  if (props.company?.competitors?.length) {
    return props.company.competitors.map((c) => (typeof c === "string" ? { name: c, ticker: c } : c));
  }
  return [];
});

const privateSide = computed(() => {
  return compsData.value?.private_side || compsData.value?.privateSide || null;
});
</script>

<template>
  <div class="rounded-xl border border-border/40 bg-card/60 p-5 backdrop-blur-md">
    <!-- Header -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-border/40 pb-3">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold text-foreground">
          <BarChart3 class="h-4 w-4 text-primary" />
          {{ t("research_desk.public_private_comps") }}
        </h3>
        <p class="text-xs text-muted-foreground">
          {{ t("research_desk.comps_subtitle") }}
        </p>
      </div>

      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-md border border-border/50 bg-background/50 px-2.5 py-1 text-xs font-medium text-foreground transition hover:bg-muted disabled:opacity-50"
        :disabled="loading"
        @click="loadComps"
      >
        <RotateCw class="h-3 w-3" :class="{ 'animate-spin': loading }" />
        <span>{{ t("research_desk.refresh") }}</span>
      </button>
    </div>

    <!-- Private Multiple Banner if available -->
    <div
      v-if="privateSide"
      class="mb-4 flex flex-wrap items-center gap-4 rounded-lg border border-purple-500/20 bg-purple-500/5 p-3 text-xs"
    >
      <span class="font-semibold text-purple-400">{{ t("research_desk.target_enterprise_multiple") }}:</span>
      <span class="font-mono font-bold text-foreground">
        {{ privateSide.multiple ? `${Number(privateSide.multiple).toFixed(1)}x EV/ARR` : "—" }}
      </span>
      <span v-if="privateSide.valuation" class="text-muted-foreground">
        {{ t("research_desk.valuation") }}: ${{ formatCompactNumber(privateSide.valuation) }}
      </span>
      <span v-if="privateSide.revenue" class="text-muted-foreground">
        {{ t("research_desk.revenue") }}: ${{ formatCompactNumber(privateSide.revenue) }}
      </span>
    </div>

    <!-- Comps Table -->
    <div v-if="peersList.length" class="overflow-x-auto">
      <table class="w-full text-left text-xs">
        <thead>
          <tr class="border-b border-border/40 text-[11px] font-semibold text-muted-foreground">
            <th class="py-2">{{ t("research_desk.peer_enterprise") }}</th>
            <th class="py-2">{{ t("research_desk.col_price") }}</th>
            <th class="py-2">{{ t("research_desk.col_market_cap") }}</th>
            <th class="py-2">{{ t("research_desk.col_ps_multiple") }}</th>
            <th class="py-2">{{ t("research_desk.col_status") }}</th>
            <th class="py-2">{{ t("research_desk.col_differentiator") }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border/20">
          <tr v-for="peer in peersList" :key="peer.ticker || peer.name" class="hover:bg-muted/30">
            <td class="py-2.5 font-medium text-foreground">
              <div class="flex items-center gap-1.5">
                <span>{{ peer.name || peer.ticker }}</span>
                <span
                  v-if="peer.ticker && peer.ticker !== '—'"
                  class="rounded bg-sky-500/10 px-1.5 py-0.2 text-[10px] font-mono text-sky-400"
                >
                  {{ peer.ticker }}
                </span>
              </div>
            </td>
            <td class="py-2.5 font-mono text-foreground">
              {{ peer.price ?? "—" }}
            </td>
            <td class="py-2.5 font-mono text-foreground">
              {{ peer.marketCap ?? peer.market_cap ?? "—" }}
            </td>
            <td class="py-2.5 font-mono font-semibold text-primary">
              {{ peer.psRatio ?? peer.ps_ratio ?? "—" }}
            </td>
            <td class="py-2.5">
              <span
                class="rounded px-1.5 py-0.5 text-[10px] font-medium"
                :class="
                  peer.status?.toLowerCase() === 'public'
                    ? 'bg-sky-500/10 text-sky-400'
                    : 'bg-purple-500/10 text-purple-400'
                "
              >
                {{ peer.status ?? "Public" }}
              </span>
            </td>
            <td class="max-w-xs truncate py-2.5 text-muted-foreground">
              {{ peer.notes || peer.differentiator || "—" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Empty State -->
    <div v-else class="py-8 text-center text-xs text-muted-foreground">
      {{ t("research_desk.no_comps") }}
    </div>
  </div>
</template>
