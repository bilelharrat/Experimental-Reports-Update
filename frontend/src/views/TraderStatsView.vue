<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CalendarClock,
  Gauge,
  Loader2,
  RefreshCw,
  TrendingUp,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";

const t = useT();

const loading = ref(true);
const refreshing = ref(false);
const error = ref(null);
const payload = ref(null);
const selectedId = ref(null);

const items = computed(() => payload.value?.items || []);
const totals = computed(() => payload.value?.totals || {});
const selectedItem = computed(() => {
  if (!items.value.length) return null;
  return (
    items.value.find((item) => item.company_id === selectedId.value) ||
    items.value[0]
  );
});
const selectedLatest = computed(() => selectedItem.value?.latest_record || null);
const selectedHistory = computed(() => selectedItem.value?.history || []);
const maxLatestTokens = computed(() =>
  Math.max(1, ...items.value.map((item) => totalTokens(latestRecord(item)))),
);

onMounted(loadStats);

async function loadStats() {
  loading.value = true;
  error.value = null;
  try {
    payload.value = await api.trader.stats(80);
    if (!selectedId.value && items.value.length) {
      selectedId.value = items.value[0].company_id;
    }
  } catch (e) {
    error.value = e?.message || t("trader_stats.load_failed");
  } finally {
    loading.value = false;
  }
}

async function refreshStats() {
  if (refreshing.value) return;
  refreshing.value = true;
  try {
    await loadStats();
  } finally {
    refreshing.value = false;
  }
}

function latestRecord(item) {
  return item?.latest_record || null;
}

function tokenUsage(record) {
  return record?.token_usage || {};
}

function totalTokens(record) {
  return Number(tokenUsage(record).total_tokens || 0);
}

function cost(record) {
  return Number(record?.cost_usd || tokenUsage(record).cost_usd || 0);
}

function changePct(record) {
  const value = record?.change_summary?.change_pct;
  return typeof value === "number" ? value : null;
}

function fmtNumber(value) {
  const number = Number(value || 0);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(
    number,
  );
}

function fmtTokens(value) {
  const number = Number(value || 0);
  if (!number) return "0";
  return new Intl.NumberFormat(undefined, {
    notation: number >= 10000 ? "compact" : "standard",
    maximumFractionDigits: number >= 10000 ? 1 : 0,
  }).format(number);
}

function fmtCost(value) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value && value < 1 ? 4 : 2,
    maximumFractionDigits: value && value < 1 ? 4 : 2,
  }).format(Number(value || 0));
}

function fmtPct(value) {
  if (typeof value !== "number") return "—";
  return `${value.toFixed(value >= 10 ? 1 : 2)}%`;
}

function fmtDuration(ms) {
  const value = Number(ms || 0);
  if (!value) return "—";
  const sec = Math.round(value / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return rem ? `${min}m ${rem}s` : `${min}m`;
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function statusLabel(record) {
  if (!record) return t("trader_stats.status_none");
  if ((record.failed_sections || []).length) return t("trader_stats.status_partial");
  if (record.baseline_seeded || record.status === "baseline") {
    return t("trader_stats.status_baseline");
  }
  return t("trader_stats.status_done");
}

function statusClass(record) {
  if (!record) return "bg-surface-muted text-ink-muted";
  if ((record.failed_sections || []).length) {
    return "bg-warning-soft text-warning-ink";
  }
  if (record.baseline_seeded || record.status === "baseline") {
    return "bg-accent-soft text-accent-ink";
  }
  return "bg-success-soft text-success-ink";
}

function changedSections(record) {
  return record?.change_summary?.changed_sections || [];
}

function sectionLabel(section) {
  return String(section || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function tokenBarWidth(record) {
  const pct = Math.round((totalTokens(record) / maxLatestTokens.value) * 100);
  return `${Math.max(2, Math.min(100, pct))}%`;
}

function historyBars(history) {
  const rows = [...(history || [])].reverse().slice(-18);
  const max = Math.max(1, ...rows.map((record) => totalTokens(record)));
  return rows.map((record) => ({
    key: `${record.recorded_at || ""}-${record.refreshed_at || ""}`,
    height: `${Math.max(8, Math.round((totalTokens(record) / max) * 100))}%`,
    title: `${fmtDate(record.refreshed_at || record.recorded_at)} · ${fmtTokens(totalTokens(record))}`,
    partial: (record.failed_sections || []).length > 0,
  }));
}

function selectItem(item) {
  selectedId.value = item.company_id;
}
</script>

<template>
  <div class="mx-auto max-w-7xl px-6 py-8 lg:px-8">
    <header
      class="flex flex-col gap-4 border-b border-subtle pb-5 lg:flex-row lg:items-start lg:justify-between"
    >
      <div class="min-w-0">
        <RouterLink
          :to="{ name: 'home' }"
          class="inline-flex items-center gap-1.5 rounded text-sm text-ink-muted hover:text-ink-primary focus-ring"
        >
          <ArrowLeft class="h-4 w-4" />
          {{ t("common.back") }}
        </RouterLink>
        <div class="mt-4 flex items-center gap-2">
          <BarChart3 class="h-5 w-5 text-accent" />
          <h1 class="font-display text-2xl font-semibold text-ink-primary">
            {{ t("trader_stats.title") }}
          </h1>
        </div>
        <p class="mt-2 max-w-3xl text-sm text-ink-secondary">
          {{ t("trader_stats.subtitle") }}
        </p>
      </div>
      <button
        type="button"
        :disabled="loading || refreshing"
        @click="refreshStats"
        class="inline-flex items-center justify-center gap-2 rounded-lg border border-subtle bg-surface px-3 py-2 text-sm font-medium text-ink-primary shadow-card hover:bg-surface-muted disabled:opacity-60 focus-ring"
      >
        <Loader2 v-if="refreshing" class="h-4 w-4 animate-spin text-accent" />
        <RefreshCw v-else class="h-4 w-4 text-accent" />
        {{ refreshing ? t("common.loading") : t("common.refresh") }}
      </button>
    </header>

    <div
      class="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5"
      aria-live="polite"
    >
      <div class="rounded-card border border-subtle bg-surface p-4 shadow-card">
        <div class="flex items-center gap-2 text-xs font-medium uppercase text-ink-muted">
          <Activity class="h-4 w-4" />
          {{ t("trader_stats.metric_symbols") }}
        </div>
        <div class="mt-2 text-2xl font-semibold text-ink-primary">
          {{ fmtNumber(totals.recorded_count || 0) }}
        </div>
      </div>
      <div class="rounded-card border border-subtle bg-surface p-4 shadow-card">
        <div class="flex items-center gap-2 text-xs font-medium uppercase text-ink-muted">
          <Gauge class="h-4 w-4" />
          {{ t("trader_stats.metric_tokens") }}
        </div>
        <div class="mt-2 text-2xl font-semibold text-ink-primary">
          {{ fmtTokens(totals.total_tokens) }}
        </div>
      </div>
      <div class="rounded-card border border-subtle bg-surface p-4 shadow-card">
        <div class="flex items-center gap-2 text-xs font-medium uppercase text-ink-muted">
          <TrendingUp class="h-4 w-4" />
          {{ t("trader_stats.metric_change") }}
        </div>
        <div class="mt-2 text-2xl font-semibold text-ink-primary">
          {{ fmtPct(totals.average_change_pct) }}
        </div>
      </div>
      <div class="rounded-card border border-subtle bg-surface p-4 shadow-card">
        <div class="flex items-center gap-2 text-xs font-medium uppercase text-ink-muted">
          <AlertTriangle class="h-4 w-4" />
          {{ t("trader_stats.metric_failed") }}
        </div>
        <div class="mt-2 text-2xl font-semibold text-ink-primary">
          {{ fmtNumber(totals.failed_section_count || 0) }}
        </div>
      </div>
      <div class="rounded-card border border-subtle bg-surface p-4 shadow-card">
        <div class="flex items-center gap-2 text-xs font-medium uppercase text-ink-muted">
          <CalendarClock class="h-4 w-4" />
          {{ t("trader_stats.metric_cost") }}
        </div>
        <div class="mt-2 text-2xl font-semibold text-ink-primary">
          {{ fmtCost(totals.cost_usd) }}
        </div>
      </div>
    </div>

    <div
      v-if="error"
      class="mt-5 rounded-card border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger-ink"
    >
      {{ error }}
    </div>

    <div v-if="loading" class="mt-10 flex items-center gap-2 text-sm text-ink-muted">
      <Loader2 class="h-4 w-4 animate-spin" />
      {{ t("trader_stats.loading") }}
    </div>

    <div
      v-else-if="!items.length"
      class="mt-10 rounded-card border border-subtle bg-surface px-6 py-8 text-center shadow-card"
    >
      <BarChart3 class="mx-auto h-8 w-8 text-ink-muted" />
      <h2 class="mt-3 font-display text-lg font-semibold text-ink-primary">
        {{ t("trader_stats.empty_title") }}
      </h2>
      <p class="mx-auto mt-2 max-w-xl text-sm text-ink-secondary">
        {{ t("trader_stats.empty_body") }}
      </p>
    </div>

    <div v-else class="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
      <section class="min-w-0 overflow-hidden rounded-card border border-subtle bg-surface shadow-card">
        <div class="border-b border-subtle px-4 py-3">
          <h2 class="text-sm font-semibold text-ink-primary">
            {{ t("trader_stats.table_title") }}
          </h2>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-subtle text-sm">
            <thead class="bg-surface-muted text-left text-xs uppercase text-ink-muted">
              <tr>
                <th class="px-4 py-3 font-medium">{{ t("trader_stats.col_symbol") }}</th>
                <th class="px-4 py-3 font-medium">{{ t("trader_stats.col_refresh") }}</th>
                <th class="px-4 py-3 font-medium">{{ t("trader_stats.col_tokens") }}</th>
                <th class="px-4 py-3 font-medium">{{ t("trader_stats.col_change") }}</th>
                <th class="px-4 py-3 font-medium">{{ t("trader_stats.col_sections") }}</th>
                <th class="px-4 py-3 font-medium">{{ t("trader_stats.col_history") }}</th>
                <th class="px-4 py-3 font-medium">{{ t("trader_stats.col_status") }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-subtle">
              <tr
                v-for="item in items"
                :key="item.company_id"
                class="cursor-pointer hover:bg-surface-muted/70"
                :class="{ 'bg-accent-soft/40': selectedItem?.company_id === item.company_id }"
                @click="selectItem(item)"
              >
                <td class="px-4 py-3">
                  <div class="font-mono font-semibold text-ink-primary">
                    {{ item.ticker || "—" }}
                  </div>
                  <div class="mt-0.5 max-w-[180px] truncate text-xs text-ink-muted">
                    {{ item.company_name }}
                  </div>
                </td>
                <td class="whitespace-nowrap px-4 py-3 text-ink-secondary">
                  {{ fmtDate(latestRecord(item)?.refreshed_at || latestRecord(item)?.recorded_at) }}
                </td>
                <td class="min-w-[150px] px-4 py-3">
                  <div class="flex items-center justify-between gap-3">
                    <span class="font-mono text-ink-primary">
                      {{ fmtTokens(totalTokens(latestRecord(item))) }}
                    </span>
                    <span class="text-xs text-ink-muted">
                      {{ fmtCost(cost(latestRecord(item))) }}
                    </span>
                  </div>
                  <div class="mt-2 h-1.5 rounded-full bg-surface-muted">
                    <div
                      class="h-1.5 rounded-full bg-accent"
                      :style="{ width: tokenBarWidth(latestRecord(item)) }"
                    />
                  </div>
                </td>
                <td class="whitespace-nowrap px-4 py-3 font-mono text-ink-primary">
                  {{ fmtPct(changePct(latestRecord(item))) }}
                </td>
                <td class="px-4 py-3">
                  <div
                    v-if="changedSections(latestRecord(item)).length"
                    class="flex max-w-[220px] flex-wrap gap-1"
                  >
                    <span
                      v-for="section in changedSections(latestRecord(item)).slice(0, 3)"
                      :key="section"
                      class="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] text-ink-secondary"
                    >
                      {{ sectionLabel(section) }}
                    </span>
                    <span
                      v-if="changedSections(latestRecord(item)).length > 3"
                      class="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] text-ink-muted"
                    >
                      +{{ changedSections(latestRecord(item)).length - 3 }}
                    </span>
                  </div>
                  <span v-else class="text-xs text-ink-muted">—</span>
                </td>
                <td class="px-4 py-3">
                  <div class="flex h-9 items-end gap-0.5">
                    <span
                      v-for="bar in historyBars(item.history)"
                      :key="bar.key"
                      :title="bar.title"
                      class="w-1.5 rounded-t"
                      :class="bar.partial ? 'bg-warning' : 'bg-accent'"
                      :style="{ height: bar.height }"
                    />
                  </div>
                </td>
                <td class="px-4 py-3">
                  <span
                    class="inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium"
                    :class="statusClass(latestRecord(item))"
                  >
                    {{ statusLabel(latestRecord(item)) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <aside class="rounded-card border border-subtle bg-surface shadow-card">
        <div class="border-b border-subtle px-4 py-3">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="font-mono text-base font-semibold text-ink-primary">
                {{ selectedItem?.ticker || "—" }}
              </div>
              <div class="truncate text-sm text-ink-muted">
                {{ selectedItem?.company_name }}
              </div>
            </div>
            <span
              class="inline-flex shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
              :class="statusClass(selectedLatest)"
            >
              {{ statusLabel(selectedLatest) }}
            </span>
          </div>
        </div>

        <div v-if="selectedLatest" class="divide-y divide-subtle">
          <section class="px-4 py-4">
            <h3 class="text-sm font-semibold text-ink-primary">
              {{ t("trader_stats.detail_run") }}
            </h3>
            <dl class="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt class="text-xs text-ink-muted">{{ t("trader_stats.detail_tokens") }}</dt>
                <dd class="mt-1 font-mono font-semibold text-ink-primary">
                  {{ fmtTokens(totalTokens(selectedLatest)) }}
                </dd>
              </div>
              <div>
                <dt class="text-xs text-ink-muted">{{ t("trader_stats.detail_cost") }}</dt>
                <dd class="mt-1 font-mono font-semibold text-ink-primary">
                  {{ fmtCost(cost(selectedLatest)) }}
                </dd>
              </div>
              <div>
                <dt class="text-xs text-ink-muted">{{ t("trader_stats.detail_wall_time") }}</dt>
                <dd class="mt-1 font-mono font-semibold text-ink-primary">
                  {{ fmtDuration(selectedLatest.duration_ms) }}
                </dd>
              </div>
              <div>
                <dt class="text-xs text-ink-muted">{{ t("trader_stats.detail_change") }}</dt>
                <dd class="mt-1 font-mono font-semibold text-ink-primary">
                  {{ fmtPct(changePct(selectedLatest)) }}
                </dd>
              </div>
            </dl>
          </section>

          <section class="px-4 py-4">
            <h3 class="text-sm font-semibold text-ink-primary">
              {{ t("trader_stats.detail_changed") }}
            </h3>
            <ul class="mt-3 space-y-2 text-sm leading-5 text-ink-secondary">
              <li
                v-for="(highlight, index) in selectedLatest.change_summary?.highlights || []"
                :key="index"
                class="flex gap-2"
              >
                <span class="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                <span>{{ highlight }}</span>
              </li>
            </ul>
          </section>

          <section class="px-4 py-4">
            <h3 class="text-sm font-semibold text-ink-primary">
              {{ t("trader_stats.detail_threads") }}
            </h3>
            <div class="mt-3 max-h-64 overflow-auto rounded-lg border border-subtle">
              <table class="min-w-full divide-y divide-subtle text-xs">
                <tbody class="divide-y divide-subtle">
                  <tr
                    v-for="thread in selectedLatest.token_usage?.by_thread || []"
                    :key="thread.thread"
                  >
                    <td class="px-3 py-2 text-ink-secondary">{{ thread.thread }}</td>
                    <td class="whitespace-nowrap px-3 py-2 text-right font-mono text-ink-primary">
                      {{ fmtTokens(thread.total_tokens) }}
                    </td>
                    <td class="whitespace-nowrap px-3 py-2 text-right font-mono text-ink-muted">
                      {{ fmtDuration(thread.duration_ms) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="px-4 py-4">
            <h3 class="text-sm font-semibold text-ink-primary">
              {{ t("trader_stats.detail_history") }}
            </h3>
            <div class="mt-3 space-y-2">
              <div
                v-for="record in selectedHistory.slice(0, 12)"
                :key="`${record.recorded_at}-${record.refreshed_at}`"
                class="rounded-lg border border-subtle px-3 py-2"
              >
                <div class="flex items-center justify-between gap-3">
                  <span class="text-xs text-ink-muted">
                    {{ fmtDate(record.refreshed_at || record.recorded_at) }}
                  </span>
                  <span class="font-mono text-xs font-semibold text-ink-primary">
                    {{ fmtTokens(totalTokens(record)) }}
                  </span>
                </div>
                <div class="mt-1 flex items-center justify-between gap-3 text-xs">
                  <span class="text-ink-muted">
                    {{ fmtDuration(record.duration_ms) }} · {{ fmtCost(cost(record)) }}
                  </span>
                  <span class="font-mono text-ink-secondary">
                    {{ fmtPct(changePct(record)) }}
                  </span>
                </div>
              </div>
            </div>
          </section>
        </div>

        <div v-else class="px-4 py-8 text-center text-sm text-ink-muted">
          {{ t("trader_stats.no_record") }}
        </div>
      </aside>
    </div>
  </div>
</template>
