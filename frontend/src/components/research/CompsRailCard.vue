<script setup>
// Web twin of MacCompsRailView.swift: comps card with the private stat tile
// row, memo source chips, editable peer list, and the fixed-column peer table
// (Peer 190 · Price 80 · 1D 70 · P/S 70 · growth 100 · margin 110 · cap 90).
import { ref, computed, watch } from "vue";
import { useT } from "../../i18n.js";
import { BarChart3, SlidersHorizontal, RotateCw, AlertTriangle, MinusCircle, FileText } from "lucide-vue-next";
import { api } from "../../api.js";
import { formatRelativeTime } from "../../formatters.js";

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
const loadFailed = ref(false);
const saving = ref(false);
const editingPeers = ref(false);
const newPeer = ref("");
const peerError = ref(null);
const compsData = ref(null);
const peerTickers = ref(null);

async function loadComps(refresh = false) {
  if (!props.companyId) return;
  loading.value = true;
  try {
    compsData.value = await api.getCompanyComps(props.companyId, refresh);
    loadFailed.value = false;
    seedPeersFromServer();
  } catch {
    compsData.value = null;
    loadFailed.value = true;
  } finally {
    loading.value = false;
  }
}

function seedPeersFromServer() {
  if (compsData.value?.peers) {
    peerTickers.value = compsData.value.peers.map((p) => p.ticker);
  }
}

watch(
  () => props.companyId,
  () => {
    editingPeers.value = false;
    peerTickers.value = null;
    peerError.value = null;
    loadComps();
  },
  { immediate: true },
);

const privateSide = computed(() => compsData.value?.private || compsData.value?.private_side || null);
const canEditPeers = computed(() => peerTickers.value != null && !loading.value);
const listedTickers = computed(() => peerTickers.value || (compsData.value?.peers || []).map((p) => p.ticker));

function fetchedPeer(ticker) {
  return (compsData.value?.peers || []).find((p) => p.ticker === ticker) || null;
}

function money(usd) {
  if (usd == null) return null;
  if (usd >= 1e12) return `$${(usd / 1e12).toFixed(2)}T`;
  if (usd >= 1e9) return `$${(usd / 1e9).toFixed(1)}B`;
  if (usd >= 1e6) return `$${(usd / 1e6).toFixed(1)}M`;
  return `$${Math.round(usd)}`;
}

function fmt(value, pattern) {
  if (value == null) return null;
  const v = Number(value);
  switch (pattern) {
    case "$2": return `$${v.toFixed(2)}`;
    case "+2%": return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
    case "1x": return `${v.toFixed(1)}x`;
    case "+0%": return `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`;
    case "0%": return `${v.toFixed(0)}%`;
    default: return String(v);
  }
}

function normalized(raw) {
  return String(raw || "").toUpperCase().replace(/[^A-Z0-9.-]/g, "");
}

async function savePeers(tickers, clearingDraft) {
  const clean = [];
  for (const raw of tickers) {
    const c = normalized(raw);
    if (c && !clean.includes(c)) clean.push(c);
  }
  const limited = clean.slice(0, 12);
  saving.value = true;
  peerError.value = null;
  try {
    await api.saveCompsPeers(props.companyId, limited);
    peerTickers.value = limited;
    if (clearingDraft) newPeer.value = "";
    await loadComps(true);
  } catch (err) {
    peerError.value = `Couldn't save peers: ${err?.message || err}`;
  } finally {
    saving.value = false;
  }
}

function addPeer() {
  const ticker = normalized(newPeer.value);
  if (!ticker || saving.value || !canEditPeers.value || !peerTickers.value) return;
  const tickers = peerTickers.value.includes(ticker)
    ? peerTickers.value
    : [...peerTickers.value, ticker];
  savePeers(tickers, true);
}

function removePeer(ticker) {
  if (saving.value || !canEditPeers.value || !peerTickers.value) return;
  savePeers(peerTickers.value.filter((p) => p !== ticker), false);
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-3.5">
    <!-- MacCardHeader("Comps", …, chart.bar.xaxis) + edit/refresh -->
    <div class="mac-cardheader">
      <span class="mac-cardheader-icon"><BarChart3 class="h-[13px] w-[13px]" stroke-width="2.4" /></span>
      <div class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-headline">{{ t("research_desk.public_private_comps") }}</span>
        <span class="mac-t-caption mac-c-secondary">{{ t("research_desk.comps_subtitle") }}</span>
      </div>
      <span class="min-w-2 flex-1" />
      <span v-if="loading || saving" class="mac-spinner" />
      <button
        type="button"
        class="mac-btn mac-btn--sm"
        :disabled="!canEditPeers"
        @click="editingPeers = !editingPeers"
      >
        <SlidersHorizontal class="h-3 w-3" />
        <span>{{ editingPeers ? t("research_desk.comps_done") : t("research_desk.comps_edit_peers") }}</span>
      </button>
      <button
        type="button"
        class="mac-btn mac-btn--sm"
        :title="t('research_desk.refresh')"
        :disabled="loading"
        @click="loadComps(true)"
      >
        <RotateCw class="h-3 w-3" />
      </button>
    </div>

    <!-- Private side stat tiles -->
    <template v-if="privateSide">
      <div class="grid grid-cols-2 gap-2.5 lg:grid-cols-5">
        <div class="mac-stattile is-compact">
          <span class="mac-t-label mac-c-secondary truncate">{{ t("research_desk.comps_post_money") }}</span>
          <span class="mac-t-metric-sm truncate">{{ money(privateSide.post_money_usd) || "—" }}</span>
        </div>
        <div class="mac-stattile is-compact">
          <span class="mac-t-label mac-c-secondary truncate">{{ t("research_desk.comps_revenue") }}</span>
          <span class="mac-t-metric-sm truncate">{{ money(privateSide.revenue_usd) || "—" }}</span>
        </div>
        <div class="mac-stattile is-compact">
          <span class="mac-t-label mac-c-secondary truncate">{{ t("research_desk.comps_implied") }}</span>
          <span class="mac-t-metric-sm truncate">{{ fmt(privateSide.implied_multiple, "1x") || "—" }}</span>
        </div>
        <div class="mac-stattile is-compact">
          <span class="mac-t-label mac-c-secondary truncate">{{ t("research_desk.comps_peer_median") }}</span>
          <span class="mac-t-metric-sm truncate">{{ fmt(compsData?.peer_median_price_to_sales, "1x") || "—" }}</span>
        </div>
        <div v-if="privateSide.vs_peer_median_pct != null" class="mac-stattile is-compact">
          <span class="mac-t-label mac-c-secondary truncate">{{ t("research_desk.comps_vs_peers") }}</span>
          <span
            class="mac-t-metric-sm truncate"
            :style="{ color: privateSide.vs_peer_median_pct <= 0 ? 'var(--mac-green)' : 'var(--mac-orange)' }"
          >
            {{ fmt(privateSide.vs_peer_median_pct, "+0%") }}
          </span>
        </div>
      </div>

      <p v-if="privateSide.implied_multiple == null" class="mac-t-caption10 mac-c-secondary">
        {{
          privateSide.post_money_usd == null
            ? t("research_desk.comps_no_post_money", { name: company?.name || companyId })
            : t("research_desk.comps_no_revenue")
        }}
      </p>

      <!-- Memo source chips -->
      <div v-if="privateSide.sources?.length" class="mac-scroll flex gap-1.5 overflow-x-auto">
        <span
          v-for="(source, idx) in privateSide.sources"
          :key="idx"
          class="mac-t-caption10 mac-c-secondary flex shrink-0 items-center gap-1 rounded-full px-1.5 py-[3px]"
          style="background: color-mix(in srgb, var(--mac-secondary) 10%, transparent)"
          :title="source.excerpt || ''"
        >
          <FileText class="h-2.5 w-2.5" />
          {{ source.field || "fact" }} · {{ source.section || "memo" }}
        </span>
      </div>
    </template>

    <!-- Edit peers row -->
    <div v-if="editingPeers" class="flex items-center gap-2">
      <input
        v-model="newPeer"
        type="text"
        class="mac-field w-[120px]"
        :placeholder="t('research_desk.comps_add_ticker')"
        :disabled="saving || !canEditPeers"
        @keydown.enter.prevent="addPeer"
      />
      <button
        type="button"
        class="mac-btn mac-btn--sm"
        :disabled="!normalized(newPeer) || saving || !canEditPeers"
        @click="addPeer"
      >
        {{ t("research_desk.comps_add") }}
      </button>
      <span v-if="peerError" class="mac-t-caption flex items-center gap-1 truncate" :style="{ color: 'var(--mac-red)' }">
        <AlertTriangle class="h-3 w-3 shrink-0" />
        {{ peerError }}
      </span>
    </div>

    <!-- Peer table on a tile -->
    <div class="mac-tile mac-scroll overflow-x-auto" style="border-radius: 10px">
      <div class="min-w-[760px]">
        <div class="mac-t-label mac-c-secondary flex items-center px-2.5 py-1.5">
          <span class="w-[190px] shrink-0">{{ t("research_desk.comps_col_peer") }}</span>
          <span class="w-[80px] shrink-0 text-right">{{ t("research_desk.comps_col_price") }}</span>
          <span class="w-[70px] shrink-0 text-right">1D</span>
          <span class="w-[70px] shrink-0 text-right">{{ t("research_desk.comps_col_ps") }}</span>
          <span class="w-[100px] shrink-0 text-right">{{ t("research_desk.comps_col_growth") }}</span>
          <span class="w-[110px] shrink-0 text-right">{{ t("research_desk.comps_col_margin") }}</span>
          <span class="flex-1" />
          <span class="w-[90px] shrink-0 text-right">{{ t("research_desk.comps_col_mktcap") }}</span>
          <span v-if="editingPeers" class="w-7 shrink-0" />
        </div>
        <div class="mac-divider" />

        <template v-if="listedTickers.length">
          <template v-for="ticker in listedTickers" :key="ticker">
            <div class="flex items-center px-2.5 py-[7px]" :title="fetchedPeer(ticker)?.source || ''">
              <span class="flex w-[190px] shrink-0 items-center gap-1.5">
                <span class="text-[12px] font-semibold">{{ ticker }}</span>
                <span class="mac-c-secondary truncate text-[12px]">{{ fetchedPeer(ticker)?.name || "" }}</span>
              </span>
              <span class="mac-mono w-[80px] shrink-0 text-right text-[12px]" :class="fetchedPeer(ticker)?.last_price == null ? 'mac-c-secondary' : ''">
                {{ fmt(fetchedPeer(ticker)?.last_price, "$2") || "—" }}
              </span>
              <span
                class="mac-mono w-[70px] shrink-0 text-right text-[12px]"
                :style="fetchedPeer(ticker)?.change_pct_1d != null ? { color: fetchedPeer(ticker).change_pct_1d >= 0 ? 'var(--mac-green)' : 'var(--mac-red)' } : { color: 'var(--mac-secondary)' }"
              >
                {{ fmt(fetchedPeer(ticker)?.change_pct_1d, "+2%") || "—" }}
              </span>
              <span class="mac-mono w-[70px] shrink-0 text-right text-[12px] font-semibold" :class="fetchedPeer(ticker)?.price_to_sales == null ? 'mac-c-secondary' : ''">
                {{ fmt(fetchedPeer(ticker)?.price_to_sales, "1x") || "—" }}
              </span>
              <span
                class="mac-mono w-[100px] shrink-0 text-right text-[12px]"
                :style="fetchedPeer(ticker)?.revenue_growth != null ? { color: fetchedPeer(ticker).revenue_growth >= 0 ? 'var(--mac-green)' : 'var(--mac-red)' } : { color: 'var(--mac-secondary)' }"
              >
                {{ fmt(fetchedPeer(ticker)?.revenue_growth, "+0%") || "—" }}
              </span>
              <span class="mac-mono w-[110px] shrink-0 text-right text-[12px]" :class="fetchedPeer(ticker)?.gross_margin == null ? 'mac-c-secondary' : ''">
                {{ fmt(fetchedPeer(ticker)?.gross_margin, "0%") || "—" }}
              </span>
              <span class="flex-1" />
              <span class="mac-mono mac-c-secondary w-[90px] shrink-0 text-right text-[12px]">
                {{ money(fetchedPeer(ticker)?.market_cap_usd) || "—" }}
              </span>
              <button
                v-if="editingPeers"
                type="button"
                class="mac-c-secondary flex w-7 shrink-0 justify-center border-none bg-transparent"
                :disabled="saving || !canEditPeers"
                @click="removePeer(ticker)"
              >
                <MinusCircle class="h-3.5 w-3.5" />
              </button>
            </div>
            <div class="mac-divider" />
          </template>
        </template>
        <div v-else-if="loadFailed && !compsData" class="flex items-center gap-2 p-2.5">
          <span class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.comps_unavailable") }}</span>
          <button type="button" class="mac-btn mac-btn--sm" @click="loadComps()">
            {{ t("research_desk.retry") }}
          </button>
        </div>
        <div v-else class="mac-t-caption10 mac-c-secondary p-2.5">
          {{ loading ? t("research_desk.comps_loading") : t("research_desk.comps_empty") }}
        </div>
      </div>
    </div>

    <p v-if="compsData?.generated_at" class="mac-t-caption10 mac-c-tertiary">
      {{ t("research_desk.comps_footer", { when: formatRelativeTime(compsData.generated_at) }) }}
    </p>
  </div>
</template>
