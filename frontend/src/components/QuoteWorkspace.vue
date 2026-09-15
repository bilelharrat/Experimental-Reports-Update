<script setup>
import { computed } from "vue";
import { formatChartStamp } from "../quoteChart.js";
import { formatCompactNumber } from "../formatters.js";
import { faLiteLines, ownershipSummary } from "../homeDesk.js";
import { optionsSnapshot } from "../marketDesk.js";
import { etfConstituents, etfContributorMoves, isKnownEtf } from "../etfConstituents.js";
import { lastPriceLabel, signedChange } from "../liveTicker.js";
import { expectedMove } from "../marketAnalytics.js";
import { useT } from "../i18n.js";

const props = defineProps({
  ticker: { type: String, default: "" },
  workspace: { type: Object, default: null },
  chartPoints: { type: Array, default: () => [] },
  chartRange: { type: String, default: "1d" },
  currency: { type: String, default: "USD" },
  loading: { type: Boolean, default: false },
  tab: { type: String, default: "profile" },
  holderMix: { type: String, default: "" },
  quotes: { type: Object, default: () => ({}) },
  lastPrice: { type: Number, default: null },
});

const emit = defineEmits(["update:tab"]);
const t = useT();

const tabs = computed(() => [
  { id: "profile", label: t("radar.tab_profile") },
  { id: "statistics", label: t("radar.tab_statistics") },
  { id: "financials", label: t("radar.tab_financials") },
  { id: "analysis", label: t("radar.tab_analysis") },
  { id: "holders", label: t("radar.tab_holders") },
  { id: "options", label: t("radar.tab_options") },
  { id: "history", label: t("radar.tab_history") },
  { id: "earnings", label: t("radar.tab_earnings") },
]);

const profile = computed(() => props.workspace?.profile || {});
const summary = computed(() => props.workspace?.summary || {});
const financials = computed(() => props.workspace?.financials || {});
const analysis = computed(() => props.workspace?.analysis || {});
const holders = computed(() => props.workspace?.holders || {});
const insiders = computed(() => props.workspace?.insiders || {});
const options = computed(() => props.workspace?.options || {});
const earnings = computed(() => props.workspace?.earnings || {});
const faLines = computed(() => faLiteLines(financials.value));
const ownSummary = computed(() => ownershipSummary(holders.value));
const optSnap = computed(() => optionsSnapshot(options.value, props.lastPrice));
const atmMove = computed(() => expectedMove(options.value?.rows || [], props.lastPrice));
const nextEarningsInMoveWindow = computed(() => {
  const move = atmMove.value;
  const next = props.workspace?.earnings?.next_date;
  if (!move || !next) return false;
  return String(next) <= String(move.expiry).slice(0, 10);
});
const etfBook = computed(() => (isKnownEtf(props.ticker) ? etfConstituents(props.ticker) : null));
const etfMoves = computed(() =>
  etfContributorMoves(etfBook.value?.holdings || [], props.quotes || {}),
);

const extraStats = computed(() => {
  const row = summary.value;
  return [
    { label: t("radar.stat_target"), value: row.one_year_target || "—" },
    { label: t("radar.stat_bid"), value: row.bid || "—" },
    { label: t("radar.stat_ask"), value: row.ask || "—" },
    { label: t("radar.stat_div_amt"), value: row.dividend || "—" },
    { label: t("radar.stat_exdiv"), value: row.ex_dividend || "—" },
    { label: t("radar.stat_beta"), value: row.beta || "—" },
    { label: t("radar.stat_alpha"), value: row.alpha || "—" },
    { label: t("radar.stat_aum"), value: row.aum || "—" },
    { label: t("radar.stat_expense"), value: row.expense_ratio || "—" },
    { label: t("radar.stat_sector"), value: row.sector || profile.value.sector || "—" },
    { label: t("radar.stat_industry"), value: row.industry || profile.value.industry || "—" },
    { label: t("radar.stat_yield"), value: row.yield || "—" },
  ];
});

const sheets = computed(() => [
  { key: "income", title: t("radar.sheet_income"), table: financials.value.income },
  { key: "balance", title: t("radar.sheet_balance"), table: financials.value.balance },
  { key: "cashflow", title: t("radar.sheet_cash"), table: financials.value.cashflow },
  { key: "ratios", title: t("radar.sheet_ratios"), table: financials.value.ratios },
]);

const historyRows = computed(() =>
  [...(props.chartPoints || [])].slice(-80).reverse(),
);

const recTotal = computed(() => {
  const row = analysis.value;
  return (row.buy || 0) + (row.hold || 0) + (row.sell || 0);
});

function money(value) {
  if (!Number.isFinite(Number(value))) return "—";
  return lastPriceLabel({ last: Number(value), currency: props.currency }) || "—";
}

function compact(value) {
  if (!Number.isFinite(Number(value))) return "—";
  return formatCompactNumber(value);
}

function yoyLabel(value) {
  if (!Number.isFinite(Number(value))) return "—";
  const n = Number(value);
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function number(value) {
  if (!Number.isFinite(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}
</script>

<template>
  <section class="yf-workspace">
    <div class="segmented mb-3" role="tablist" :aria-label="t('radar.workspace_label')">
      <button
        v-for="item in tabs"
        :key="item.id"
        type="button"
        class="segmented-item focus-ring"
        role="tab"
        :data-selected="tab === item.id"
        :aria-selected="tab === item.id"
        @click="emit('update:tab', item.id)"
      >
        {{ item.label }}
      </button>
    </div>
    <p v-if="loading" class="px-1 py-6 text-callout text-ink-muted">{{ t("common.loading") }}</p>
    <template v-else>
      <div v-if="tab === 'profile'" class="space-y-3">
        <p class="text-callout text-ink-primary">
          {{ profile.description || t("radar.profile_empty") }}
        </p>
        <div v-if="etfBook" class="space-y-2 rounded-md border border-[rgb(var(--color-border-subtle))] bg-[rgb(var(--color-fill-tertiary)/0.45)] px-3 py-2">
          <h3 class="text-footnote font-semibold uppercase tracking-[0.06em] text-notice">
            {{ t("radar.etf_label") }}
          </h3>
          <p class="text-caption1 font-medium text-ink-secondary">{{ t("radar.etf_illustrative") }}</p>
          <p class="text-caption1 text-ink-muted">{{ etfBook.name }} · {{ etfBook.asOf }}</p>
          <div class="yf-fin-scroll">
            <table class="yf-fin-table">
              <thead>
                <tr>
                  <th>{{ t("radar.col_symbol") }}</th>
                  <th>{{ t("radar.col_weight") }}</th>
                  <th>{{ t("radar.col_change") }}</th>
                  <th>{{ t("radar.col_contrib") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in etfMoves" :key="row.ticker">
                  <th>{{ row.ticker }}</th>
                  <td>{{ row.weight.toFixed(1) }}%</td>
                  <td :class="(row.change || 0) >= 0 ? 'text-success' : 'text-danger'">
                    {{ row.change != null ? signedChange(row.change) : "—" }}
                  </td>
                  <td :class="(row.contribution || 0) >= 0 ? 'text-success' : 'text-danger'">
                    {{ row.contribution != null ? `${row.contribution >= 0 ? "+" : ""}${row.contribution.toFixed(2)}` : "—" }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <dl class="yf-stats">
          <div class="yf-stat">
            <dt>{{ t("radar.stat_sector") }}</dt>
            <dd>{{ profile.sector || summary.sector || "—" }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.stat_industry") }}</dt>
            <dd>{{ profile.industry || summary.industry || "—" }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.stat_region") }}</dt>
            <dd>{{ profile.region || "—" }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.stat_website") }}</dt>
            <dd>{{ profile.website || "—" }}</dd>
          </div>
        </dl>
      </div>

      <dl v-else-if="tab === 'statistics'" class="yf-stats">
        <div v-for="stat in extraStats" :key="stat.label" class="yf-stat">
          <dt>{{ stat.label }}</dt>
          <dd>{{ stat.value }}</dd>
        </div>
      </dl>

      <div v-else-if="tab === 'financials'" class="space-y-5">
        <div v-if="faLines.length" class="space-y-2">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-footnote font-semibold text-ink-muted">
              {{ t("radar.fa_lite_label") }}
            </h3>
            <span class="text-caption1 text-ink-muted">{{ t("radar.fa_yoy") }}</span>
          </div>
          <dl class="yf-stats">
            <div v-for="line in faLines" :key="line.id" class="yf-stat">
              <dt>{{ line.label }}</dt>
              <dd>
                {{ line.latestRaw }}
                <span
                  v-if="line.yoy != null"
                  class="ml-1 text-caption1"
                  :class="line.yoy >= 0 ? 'text-success' : 'text-danger'"
                >
                  {{ yoyLabel(line.yoy) }}
                </span>
              </dd>
            </div>
          </dl>
        </div>
        <div v-for="sheet in sheets" :key="sheet.key">
          <h3 class="mb-2 text-footnote font-semibold text-ink-muted">
            {{ sheet.title }}
          </h3>
          <p v-if="!sheet.table?.rows?.length" class="text-callout text-ink-muted">
            {{ t("radar.financials_empty") }}
          </p>
          <div v-else class="yf-fin-scroll">
            <table class="yf-fin-table">
              <thead>
                <tr>
                  <th></th>
                  <th v-for="header in sheet.table.headers" :key="header">{{ header }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in sheet.table.rows" :key="row.label" :data-section="row.section">
                  <th>{{ row.label }}</th>
                  <td v-for="(value, index) in row.values" :key="`${row.label}-${index}`">{{ value || "—" }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-else-if="tab === 'analysis'" class="space-y-4">
        <div class="yf-stats">
          <div class="yf-stat">
            <dt>{{ t("radar.stat_target") }}</dt>
            <dd>{{ money(analysis.target) }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.stat_target_low") }}</dt>
            <dd>{{ money(analysis.target_low) }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.stat_target_high") }}</dt>
            <dd>{{ money(analysis.target_high) }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.rec_buy") }}</dt>
            <dd>{{ analysis.buy || 0 }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.rec_hold") }}</dt>
            <dd>{{ analysis.hold || 0 }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.rec_sell") }}</dt>
            <dd>{{ analysis.sell || 0 }}</dd>
          </div>
        </div>
        <p v-if="recTotal" class="text-footnote text-ink-secondary">
          {{ t("radar.rec_total", { n: recTotal }) }}
        </p>
        <div class="yf-fin-scroll">
          <table class="yf-fin-table">
            <thead>
              <tr>
                <th>{{ t("radar.col_period") }}</th>
                <th>{{ t("radar.col_eps") }}</th>
                <th>{{ t("radar.col_high") }}</th>
                <th>{{ t("radar.col_low") }}</th>
                <th>{{ t("radar.col_estimates") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in (analysis.quarterly || [])" :key="`q-${row.period}`">
                <th>{{ row.period }}</th>
                <td>{{ row.consensus ?? "—" }}</td>
                <td>{{ row.high ?? "—" }}</td>
                <td>{{ row.low ?? "—" }}</td>
                <td>{{ row.estimates ?? "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="tab === 'holders'" class="space-y-4">
        <dl class="yf-stats">
          <div class="yf-stat">
            <dt>{{ t("radar.stat_inst_own") }}</dt>
            <dd>{{ holders.ownership_pct || "—" }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.stat_shares_out") }}</dt>
            <dd>{{ holders.shares_out || "—" }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.stat_holdings_value") }}</dt>
            <dd>{{ holders.holdings_value || "—" }}</dd>
          </div>
        </dl>
        <p v-if="holderMix" class="text-footnote text-ink-secondary">
          {{ t("radar.holder_mix", { mix: holderMix }) }}
        </p>
        <div v-if="ownSummary.buyers.length || ownSummary.sellers.length" class="grid gap-3 sm:grid-cols-2">
          <div>
            <h3 class="mb-1 text-footnote font-semibold text-ink-muted">
              {{ t("radar.own_buyers") }}
            </h3>
            <ul class="space-y-1 text-footnote text-ink-primary">
              <li v-for="row in ownSummary.buyers" :key="`b-${row.owner}`">
                {{ row.owner }}
                <span class="text-success">{{ row.change_pct }}</span>
              </li>
            </ul>
          </div>
          <div>
            <h3 class="mb-1 text-footnote font-semibold text-ink-muted">
              {{ t("radar.own_sellers") }}
            </h3>
            <ul class="space-y-1 text-footnote text-ink-primary">
              <li v-for="row in ownSummary.sellers" :key="`s-${row.owner}`">
                {{ row.owner }}
                <span class="text-danger">{{ row.change_pct }}</span>
              </li>
            </ul>
          </div>
        </div>
        <div class="yf-fin-scroll">
          <table class="yf-fin-table">
            <thead>
              <tr>
                <th>{{ t("radar.col_holder") }}</th>
                <th>{{ t("radar.col_shares") }}</th>
                <th>{{ t("radar.col_change") }}</th>
                <th>{{ t("radar.col_value") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in (holders.holders || [])" :key="row.owner">
                <th>{{ row.owner }}</th>
                <td>{{ row.shares }}</td>
                <td>{{ row.change_pct }}</td>
                <td>{{ row.value }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="insiders.summary?.length" class="yf-fin-scroll">
          <table class="yf-fin-table">
            <thead>
              <tr>
                <th>{{ t("radar.col_insider") }}</th>
                <th>{{ t("radar.col_3m") }}</th>
                <th>{{ t("radar.col_12m") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in insiders.summary" :key="row.label">
                <th>{{ row.label }}</th>
                <td>{{ row.months3 }}</td>
                <td>{{ row.months12 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="tab === 'options'" class="space-y-4">
        <div
          v-if="atmMove"
          class="rounded-md bg-surface-secondary px-3 py-2"
          data-testid="expected-move"
        >
          <span class="text-footnote font-semibold text-ink-muted">
            {{ t("radar.opt_expected_move") }}
          </span>
          <span class="ml-2 mono-data text-callout font-semibold tabular text-ink-primary">
            ±{{ atmMove.movePct.toFixed(1) }}%
          </span>
          <span class="ml-1 text-caption1 text-ink-muted">
            {{ t("radar.opt_expected_move_by", { date: atmMove.expiry, n: atmMove.days }) }}
          </span>
          <span
            v-if="nextEarningsInMoveWindow"
            class="ml-2 rounded-pill bg-notice/15 px-1.5 py-0.5 text-caption2 font-semibold text-notice"
          >
            {{ t("radar.opt_earnings_inside") }}
          </span>
        </div>
        <dl v-if="optSnap.rowCount" class="yf-stats">
          <div class="yf-stat">
            <dt>{{ t("radar.opt_nearest") }}</dt>
            <dd>{{ optSnap.nearestExpiry || "—" }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.opt_atm") }}</dt>
            <dd>{{ optSnap.atmStrike != null ? number(optSnap.atmStrike) : "—" }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.opt_pcr_vol") }}</dt>
            <dd>{{ optSnap.putCallVolume != null ? optSnap.putCallVolume.toFixed(2) : "—" }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.opt_pcr_oi") }}</dt>
            <dd>{{ optSnap.putCallOi != null ? optSnap.putCallOi.toFixed(2) : "—" }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.opt_call_vol") }}</dt>
            <dd>{{ compact(optSnap.callVolume) }}</dd>
          </div>
          <div class="yf-stat">
            <dt>{{ t("radar.opt_put_vol") }}</dt>
            <dd>{{ compact(optSnap.putVolume) }}</dd>
          </div>
        </dl>
        <div class="yf-fin-scroll">
          <p v-if="!(options.rows || []).length" class="text-callout text-ink-muted">
            {{ t("radar.options_empty") }}
          </p>
          <table v-else class="yf-fin-table">
            <thead>
              <tr>
                <th>{{ t("radar.col_expiry") }}</th>
                <th>{{ t("radar.col_call") }}</th>
                <th>{{ t("radar.col_strike") }}</th>
                <th>{{ t("radar.col_put") }}</th>
                <th>{{ t("radar.col_volume") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in options.rows" :key="`${row.expiry}-${row.strike}`">
                <th>{{ row.expiry }}</th>
                <td>{{ row.call_last }}</td>
                <td>{{ row.strike }}</td>
                <td>{{ row.put_last }}</td>
                <td>{{ row.call_volume }} / {{ row.put_volume }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="tab === 'history'" class="yf-fin-scroll">
        <table class="yf-fin-table">
          <thead>
            <tr>
              <th>{{ t("radar.col_date") }}</th>
              <th>{{ t("radar.col_open") }}</th>
              <th>{{ t("radar.col_high") }}</th>
              <th>{{ t("radar.col_low") }}</th>
              <th>{{ t("radar.col_price") }}</th>
              <th>{{ t("radar.col_volume") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in historyRows" :key="row.t">
              <th>{{ formatChartStamp(row.t, chartRange) }}</th>
              <td>{{ money(row.open) }}</td>
              <td>{{ money(row.high) }}</td>
              <td>{{ money(row.low) }}</td>
              <td>{{ money(row.close) }}</td>
              <td>{{ compact(row.volume) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else-if="tab === 'earnings'" class="space-y-4">
        <dl class="yf-stats">
          <div class="yf-stat">
            <dt>{{ t("radar.stat_next_earn") }}</dt>
            <dd>
              {{ earnings.next_date || "—" }}
              <span v-if="earnings.next_estimated" class="text-caption1 text-ink-muted">
                {{ t("radar.earn_estimated") }}
              </span>
            </dd>
          </div>
        </dl>
        <p v-if="!(earnings.past || []).length" class="text-callout text-ink-muted">
          {{ t("radar.earnings_empty") }}
        </p>
        <div v-else class="yf-fin-scroll">
          <table class="yf-fin-table">
            <thead>
              <tr>
                <th>{{ t("radar.col_period") }}</th>
                <th>{{ t("radar.col_date") }}</th>
                <th>{{ t("radar.col_eps") }}</th>
                <th>{{ t("radar.col_estimates") }}</th>
                <th>{{ t("radar.col_surprise") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in earnings.past" :key="`${row.period}-${row.reported}`">
                <th>{{ row.period }}</th>
                <td>{{ row.reported || "—" }}</td>
                <td>{{ row.eps ?? "—" }}</td>
                <td>{{ row.estimate ?? "—" }}</td>
                <td>{{ row.surprise_pct != null ? `${row.surprise_pct}%` : "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </section>
</template>
