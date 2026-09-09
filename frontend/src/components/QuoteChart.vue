<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  chartCsv,
  chartDirection,
  chartDragStats,
  chartGeometry,
  drawdownSeries,
  eventMarkers,
  fibonacciLevels,
  formatChartDuration,
  formatChartStamp,
  maxDrawdown,
  monthlySeasonality,
  movingAverage,
  nearestChartCoord,
  volumeWeightedAverage,
  overlayPath,
  relativeSeries,
  relativeStrength,
} from "../quoteChart.js";
import { volumeProfile, vwapBands } from "../marketAnalytics.js";
import { loadChartPrefs, saveChartPrefs } from "../marketDesk.js";
import { lastPriceLabel } from "../liveTicker.js";
import { useT } from "../i18n.js";

const props = defineProps({
  points: { type: Array, default: () => [] },
  previousClose: { type: Number, default: null },
  range: { type: String, default: "1d" },
  currency: { type: String, default: "USD" },
  loading: { type: Boolean, default: false },
  ticker: { type: String, default: "" },
  events: { type: Array, default: () => [] },
  peerSeries: { type: Array, default: () => [] },
  /** Taller plot for the expanded full-width desk. */
  tall: { type: Boolean, default: false },
});

const t = useT();
const prefs = loadChartPrefs();
const rootEl = ref(null);
const hover = ref(null);
const dragOrigin = ref(null);
const selection = ref(null);
const showSma20 = ref(prefs.sma20);
const showSma50 = ref(prefs.sma50);
const showSma200 = ref(prefs.sma200);
const showVwap = ref(props.range === "1d" ? prefs.vwap : prefs.vwap);
const showVolume = ref(prefs.volume);
const showRsi = ref(prefs.rsi);
const showPeers = ref(true);
const showEvents = ref(true);
const showLog = ref(prefs.logScale);
const showDrawdown = ref(false);
const showSeasonality = ref(false);
const showProfile = ref(false);
const showVwapBands = ref(false);
const relativeMode = ref(false);
const pad = 18;
const width = ref(720);
const height = computed(() => (props.tall ? 400 : 280));
const paneH = 72;
const plotRight = computed(() => Math.max(width.value - pad, pad));
const mainViewBox = computed(() => `0 0 ${width.value} ${height.value}`);
const paneViewBox = computed(() => `0 0 ${width.value} ${paneH}`);

let resizeObserver = null;

function syncWidth() {
  const next = Math.round(rootEl.value?.clientWidth || 0);
  if (next >= 240 && next !== width.value) width.value = next;
}

onMounted(() => {
  syncWidth();
  if (typeof ResizeObserver === "undefined" || !rootEl.value) return;
  resizeObserver = new ResizeObserver(() => syncWidth());
  resizeObserver.observe(rootEl.value);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  resizeObserver = null;
});

watch(width, () => {
  selection.value = null;
  dragOrigin.value = null;
  hover.value = null;
});

watch(
  () => props.tall,
  () => {
    selection.value = null;
    dragOrigin.value = null;
    hover.value = null;
  },
);

function persistPrefs() {
  saveChartPrefs({
    sma20: showSma20.value,
    sma50: showSma50.value,
    sma200: showSma200.value,
    vwap: showVwap.value,
    logScale: showLog.value,
    volume: showVolume.value,
    rsi: showRsi.value,
  });
}

watch([showSma20, showSma50, showSma200, showVwap, showLog, showVolume, showRsi], persistPrefs);

const geometry = computed(() => {
  if (relativeMode.value && props.peerSeries?.length) {
    const series = relativeSeries(props.points);
    const fakePoints = series.map((close, index) => ({
      t: props.points[index]?.t,
      close,
    }));
    return chartGeometry(fakePoints, { width: width.value, height: height.value, pad, logScale: false });
  }
  return chartGeometry(props.points, {
    width: width.value,
    height: height.value,
    pad,
    logScale: showLog.value && !relativeMode.value,
  });
});
const sma20 = computed(() => movingAverage(props.points, 20));
const sma50 = computed(() => movingAverage(props.points, 50));
const sma200 = computed(() => movingAverage(props.points, 200));
const vwap = computed(() => volumeWeightedAverage(props.points));
const vwapPath = computed(() =>
  relativeMode.value ? "" : overlayPath(vwap.value, geometry.value, { height: height.value, pad }),
);
const rsi = computed(() => relativeStrength(props.points, 14));
const sma20Path = computed(() =>
  relativeMode.value ? "" : overlayPath(sma20.value, geometry.value, { height: height.value, pad }),
);
const sma50Path = computed(() =>
  relativeMode.value ? "" : overlayPath(sma50.value, geometry.value, { height: height.value, pad }),
);
const sma200Path = computed(() =>
  relativeMode.value ? "" : overlayPath(sma200.value, geometry.value, { height: height.value, pad }),
);
const rsiGeometry = computed(() => ({
  min: 0,
  max: 100,
  coords: geometry.value.coords,
}));
const rsiPath = computed(() => overlayPath(rsi.value, rsiGeometry.value, { height: paneH, pad: 8 }));
const hasVolume = computed(() =>
  (props.points || []).some((point) => Number.isFinite(Number(point?.volume))),
);
const volumeMax = computed(() => {
  const values = (props.points || []).map((point) => Number(point?.volume)).filter(Number.isFinite);
  return Math.max(...values, 1);
});
const peerPaths = computed(() => {
  if (!showPeers.value || !props.peerSeries?.length) return [];
  const palette = [
    "rgb(var(--color-accent))",
    "rgb(var(--color-text-secondary))",
    "rgb(var(--color-notice))",
    "rgb(var(--color-text-muted))",
  ];
  return props.peerSeries.slice(0, 4).map((series, index) => {
    const values = relativeMode.value
      ? relativeSeries(series.points || [])
      : (series.points || []).map((point) => Number(point?.close));
    return {
      ticker: series.ticker,
      path: overlayPath(values, geometry.value, { height: height.value, pad }),
      stroke: palette[index % palette.length],
    };
  });
});
const markers = computed(() => {
  if (!showEvents.value) return [];
  const events = eventMarkers(props.points, props.events);
  return events
    .map((event) => {
      const coord = geometry.value.coords.find((row) => Number(row.point?.t) === Number(event.t));
      return coord ? { ...event, x: coord.x, y: coord.y } : null;
    })
    .filter(Boolean);
});
const prevLine = computed(() => {
  if (relativeMode.value || showLog.value) return null;
  const prev = Number(props.previousClose);
  const geo = geometry.value;
  if (!Number.isFinite(prev) || !geo.coords.length) return null;
  const h = height.value;
  const innerH = h - pad * 2;
  const span = geo.max - geo.min || 1;
  const y = pad + (1 - (prev - geo.min) / span) * innerH;
  if (y < pad || y > h - pad) return null;
  return y;
});
const up = computed(() => chartDirection(props.points, props.previousClose) >= 0);
const stroke = computed(() =>
  up.value ? "rgb(var(--color-success))" : "rgb(var(--color-danger))",
);
const fill = computed(() =>
  up.value ? "rgb(var(--color-success) / 0.16)" : "rgb(var(--color-danger) / 0.16)",
);
const stats = computed(() =>
  chartDragStats(selection.value?.start, selection.value?.end, geometry.value.coords),
);
const fibs = computed(() =>
  stats.value ? fibonacciLevels(stats.value.high, stats.value.low) : [],
);
const selectionUp = computed(() => (stats.value?.change ?? 0) >= 0);
const selectionFill = computed(() =>
  selectionUp.value
    ? "rgb(var(--color-success) / 0.14)"
    : "rgb(var(--color-danger) / 0.14)",
);
const selectionStroke = computed(() =>
  selectionUp.value ? "rgb(var(--color-success))" : "rgb(var(--color-danger))",
);
const dd = computed(() => maxDrawdown(props.points));
const ddSeries = computed(() => drawdownSeries(props.points));
const ddGeometry = computed(() => {
  const values = ddSeries.value.filter(Number.isFinite);
  if (!values.length) return { min: -1, max: 0, coords: geometry.value.coords };
  return {
    min: Math.min(...values, -1),
    max: 0,
    coords: geometry.value.coords,
  };
});
const ddPath = computed(() => overlayPath(ddSeries.value, ddGeometry.value, { height: paneH, pad: 8 }));
const seasonality = computed(() => monthlySeasonality(props.points));
const monthLabels = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const profile = computed(() => volumeProfile(props.points, { buckets: 18 }));
const bands = computed(() => vwapBands(props.points));
const bandUpper1 = computed(() =>
  overlayPath(
    bands.value.map((row) => row.upper1),
    geometry.value,
    { height: height.value, pad },
  ),
);
const bandLower1 = computed(() =>
  overlayPath(
    bands.value.map((row) => row.lower1),
    geometry.value,
    { height: height.value, pad },
  ),
);
const bandUpper2 = computed(() =>
  overlayPath(
    bands.value.map((row) => row.upper2),
    geometry.value,
    { height: height.value, pad },
  ),
);
const bandLower2 = computed(() =>
  overlayPath(
    bands.value.map((row) => row.lower2),
    geometry.value,
    { height: height.value, pad },
  ),
);

watch(
  () => [props.range, props.points],
  ([range]) => {
    selection.value = null;
    dragOrigin.value = null;
    hover.value = null;
    if (range === "1d") {
      showVwap.value = true;
    } else {
      showVwap.value = false;
      showVwapBands.value = false;
      showSma20.value = true;
      showSma50.value = true;
    }
  },
);

function money(value) {
  return lastPriceLabel({ last: Number(value), currency: props.currency }) || "—";
}

function signedMoney(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const abs = lastPriceLabel({ last: Math.abs(n), currency: props.currency }) || "";
  if (!abs) return "—";
  if (n > 0) return `+${abs}`;
  if (n < 0) return `-${abs.replace(/^[-+]/, "")}`;
  return abs;
}

function svgX(event) {
  const svg = event.currentTarget;
  const box = svg.getBoundingClientRect();
  return ((event.clientX - box.left) / box.width) * width.value;
}

function pick(event) {
  return nearestChartCoord(geometry.value.coords, svgX(event));
}

function onPointerDown(event) {
  if (event.button != null && event.button !== 0) return;
  const coord = pick(event);
  if (!coord) return;
  event.currentTarget.setPointerCapture?.(event.pointerId);
  dragOrigin.value = coord;
  selection.value = null;
  hover.value = coord;
}

function onMove(event) {
  const coord = pick(event);
  if (!coord) return;
  if (dragOrigin.value) {
    hover.value = coord;
    if (coord.point !== dragOrigin.value.point) {
      selection.value = { start: dragOrigin.value, end: coord };
    }
    return;
  }
  if (!selection.value) hover.value = coord;
}

function onPointerUp() {
  dragOrigin.value = null;
}

function onLeave() {
  if (dragOrigin.value || selection.value) return;
  hover.value = null;
}

function fibY(value) {
  const geo = geometry.value;
  const h = height.value;
  const innerH = h - pad * 2;
  const span = geo.max - geo.min || 1;
  let mapped = Number(value);
  if (geo.logScale && mapped > 0) mapped = Math.log(mapped);
  return pad + (1 - (mapped - geo.min) / span) * innerH;
}

function volumeY(volume) {
  const n = Number(volume);
  if (!Number.isFinite(n)) return paneH - 4;
  return paneH - 4 - (n / volumeMax.value) * (paneH - 12);
}

function seasonBar(avg) {
  const n = Number(avg);
  if (!Number.isFinite(n)) return 4;
  return Math.min(36, Math.max(4, Math.abs(n) * 8));
}

function exportCsv() {
  const blob = new Blob([chartCsv(props.points)], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${props.ticker || "chart"}-${props.range}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

const hoverLabel = computed(() => {
  if (selection.value || !hover.value) return "";
  const price = money(hover.value.value);
  const when = formatChartStamp(hover.value.point?.t, props.range);
  return [price, when].filter(Boolean).join(" · ");
});

const selectionDelta = computed(() => {
  if (!stats.value) return "";
  const pct = `${stats.value.changePct >= 0 ? "+" : ""}${stats.value.changePct.toFixed(2)}%`;
  return `${signedMoney(stats.value.change)} (${pct}) · ${formatChartDuration(stats.value.durationSec)}`;
});

const selectionSpan = computed(() => {
  if (!selection.value) return "";
  const start = formatChartStamp(selection.value.start.point?.t, props.range);
  const end = formatChartStamp(selection.value.end.point?.t, props.range);
  const prices = `${money(stats.value?.start)} → ${money(stats.value?.end)}`;
  if (start && end) return `${prices} · ${start} → ${end}`;
  return prices;
});
</script>

<template>
  <div ref="rootEl" class="yf-chart" :data-tall="tall ? 'true' : 'false'">
    <div class="yf-chart-tools yf-chart-tools-grouped">
      <div class="yf-chart-tool-group" role="group" :aria-label="t('radar.chart_overlays')">
        <span class="yf-chart-tool-label">{{ t("radar.chart_overlays") }}</span>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showSma20" @click="showSma20 = !showSma20">
          {{ t("radar.ind_sma20") }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showSma50" @click="showSma50 = !showSma50">
          {{ t("radar.ind_sma50") }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showSma200" @click="showSma200 = !showSma200">
          {{ t("radar.ind_sma200") }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showVwap" @click="showVwap = !showVwap">
          {{ t("radar.ind_vwap") }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showVwapBands" @click="showVwapBands = !showVwapBands">
          {{ t("radar.ind_vwap_bands") }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showLog" @click="showLog = !showLog">
          {{ t("radar.ind_log") }}
        </button>
        <button
          v-if="peerSeries.length"
          type="button"
          class="yf-range-item focus-ring"
          :data-selected="showPeers"
          @click="showPeers = !showPeers"
        >
          {{ t("radar.ind_peers") }}
        </button>
        <button
          v-if="peerSeries.length"
          type="button"
          class="yf-range-item focus-ring"
          :data-selected="relativeMode"
          @click="relativeMode = !relativeMode"
        >
          {{ t("radar.ind_relative") }}
        </button>
        <button
          v-if="events.length"
          type="button"
          class="yf-range-item focus-ring"
          :data-selected="showEvents"
          @click="showEvents = !showEvents"
        >
          {{ t("radar.ind_earnings") }}
        </button>
      </div>
      <div class="yf-chart-tool-group" role="group" :aria-label="t('radar.chart_panes')">
        <span class="yf-chart-tool-label">{{ t("radar.chart_panes") }}</span>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showVolume" @click="showVolume = !showVolume">
          {{ t("radar.ind_volume") }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showProfile" @click="showProfile = !showProfile">
          {{ t("radar.ind_profile") }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showRsi" @click="showRsi = !showRsi">
          {{ t("radar.ind_rsi") }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showDrawdown" @click="showDrawdown = !showDrawdown">
          {{ t("radar.ind_drawdown") }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showSeasonality" @click="showSeasonality = !showSeasonality">
          {{ t("radar.ind_seasonality") }}
        </button>
      </div>
      <div class="yf-chart-tool-group" role="group" :aria-label="t('radar.chart_export')">
        <span class="yf-chart-tool-label">{{ t("radar.chart_export") }}</span>
        <button type="button" class="yf-range-item focus-ring" @click="exportCsv">
          {{ t("radar.export_csv") }}
        </button>
      </div>
    </div>
    <p v-if="loading" class="px-1 py-16 text-center text-callout text-ink-muted">
      {{ t("common.loading") }}
    </p>
    <p
      v-else-if="!points.length"
      class="px-1 py-16 text-center text-callout text-ink-muted"
    >
      {{ t("radar.chart_empty") }}
    </p>
    <svg
      v-else
      class="yf-chart-svg"
      :viewBox="mainViewBox"
      preserveAspectRatio="none"
      role="img"
      :aria-label="t('radar.chart_label')"
      @pointerdown="onPointerDown"
      @pointermove="onMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onLeave"
    >
      <path :d="geometry.area" :fill="fill" />
      <rect
        v-if="selection"
        :x="Math.min(selection.start.x, selection.end.x)"
        :y="pad"
        :width="Math.max(Math.abs(selection.end.x - selection.start.x), 1)"
        :height="height - pad * 2"
        :fill="selectionFill"
      />
      <line
        v-if="prevLine != null"
        :x1="pad"
        :x2="plotRight"
        :y1="prevLine"
        :y2="prevLine"
        stroke="rgb(var(--color-text-muted))"
        stroke-dasharray="4 4"
        stroke-width="1"
      />
      <g v-if="selection">
        <line
          v-for="level in fibs"
          :key="level.ratio"
          :x1="pad"
          :x2="plotRight"
          :y1="fibY(level.value)"
          :y2="fibY(level.value)"
          stroke="rgb(var(--color-text-secondary))"
          stroke-dasharray="2 4"
          stroke-width="1"
        />
      </g>
      <path v-if="showSma20 && sma20Path" :d="sma20Path" fill="none" stroke="rgb(var(--color-accent))" stroke-width="1.25" />
      <path v-if="showSma50 && sma50Path" :d="sma50Path" fill="none" stroke="rgb(var(--color-text-secondary))" stroke-width="1.25" />
      <path v-if="showSma200 && sma200Path" :d="sma200Path" fill="none" stroke="rgb(var(--color-notice))" stroke-width="1.4" />
      <path
        v-if="showVwap && vwapPath"
        :d="vwapPath"
        fill="none"
        stroke="rgb(var(--color-notice))"
        stroke-width="1.35"
        stroke-dasharray="5 3"
      />
      <path
        v-if="showVwapBands && bandUpper2"
        :d="bandUpper2"
        fill="none"
        stroke="rgb(var(--color-text-muted))"
        stroke-width="1"
        stroke-dasharray="2 4"
        opacity="0.7"
      />
      <path
        v-if="showVwapBands && bandLower2"
        :d="bandLower2"
        fill="none"
        stroke="rgb(var(--color-text-muted))"
        stroke-width="1"
        stroke-dasharray="2 4"
        opacity="0.7"
      />
      <path
        v-if="showVwapBands && bandUpper1"
        :d="bandUpper1"
        fill="none"
        stroke="rgb(var(--color-accent))"
        stroke-width="1.1"
        stroke-dasharray="3 3"
        opacity="0.85"
      />
      <path
        v-if="showVwapBands && bandLower1"
        :d="bandLower1"
        fill="none"
        stroke="rgb(var(--color-accent))"
        stroke-width="1.1"
        stroke-dasharray="3 3"
        opacity="0.85"
      />
      <path
        v-for="peer in peerPaths"
        :key="peer.ticker"
        :d="peer.path"
        fill="none"
        :stroke="peer.stroke"
        stroke-width="1.25"
        stroke-dasharray="4 3"
        opacity="0.85"
      />
      <path :d="geometry.line" fill="none" :stroke="stroke" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
      <g v-for="marker in markers" :key="`${marker.t}-${marker.label}`">
        <line
          :x1="marker.x"
          :x2="marker.x"
          :y1="pad"
          :y2="height - pad"
          :stroke="marker.kind === 'split' ? 'rgb(var(--color-danger))' : marker.kind === 'dividend' ? 'rgb(var(--color-accent))' : 'rgb(var(--color-notice))'"
          stroke-dasharray="2 3"
          stroke-width="1"
        />
        <circle
          :cx="marker.x"
          :cy="pad"
          r="3.5"
          :fill="marker.kind === 'split' ? 'rgb(var(--color-danger))' : marker.kind === 'dividend' ? 'rgb(var(--color-accent))' : 'rgb(var(--color-notice))'"
        />
        <text :x="marker.x + 4" :y="pad - 2" class="yf-rrg-label">{{ marker.label }}</text>
      </g>
      <g v-if="selection">
        <line :x1="selection.start.x" :x2="selection.start.x" :y1="pad" :y2="height - pad" :stroke="selectionStroke" stroke-width="1" />
        <line :x1="selection.end.x" :x2="selection.end.x" :y1="pad" :y2="height - pad" :stroke="selectionStroke" stroke-width="1" />
        <circle :cx="selection.start.x" :cy="selection.start.y" r="4" :fill="selectionStroke" />
        <circle :cx="selection.end.x" :cy="selection.end.y" r="4" :fill="selectionStroke" />
      </g>
      <g v-else-if="hover">
        <line :x1="hover.x" :x2="hover.x" :y1="pad" :y2="height - pad" stroke="rgb(var(--color-text-muted))" stroke-dasharray="3 3" />
        <circle :cx="hover.x" :cy="hover.y" r="4" :fill="stroke" />
      </g>
    </svg>
    <div
      v-if="!loading && points.length && showProfile && profile.length"
      class="yf-profile"
      :aria-label="t('radar.ind_profile')"
    >
      <div
        v-for="row in profile"
        :key="row.index"
        class="yf-profile-row"
        :title="`${money(row.mid)} · ${Math.round(row.pct)}%`"
      >
        <span class="yf-profile-bar" :style="{ width: `${Math.max(row.pct, 2)}%` }"></span>
      </div>
    </div>
    <svg
      v-if="!loading && points.length && showVolume && hasVolume"
      class="yf-chart-pane"
      :viewBox="paneViewBox"
      preserveAspectRatio="none"
      role="img"
      :aria-label="t('radar.ind_volume')"
    >
      <rect
        v-for="(coord, index) in geometry.coords"
        :key="`v-${index}`"
        :x="coord.x - 1.2"
        :y="volumeY(coord.point?.volume)"
        width="2.4"
        :height="Math.max(paneH - 4 - volumeY(coord.point?.volume), 0)"
        :fill="stroke"
        opacity="0.45"
      />
    </svg>
    <svg
      v-if="!loading && points.length && showRsi && rsiPath"
      class="yf-chart-pane"
      :viewBox="paneViewBox"
      preserveAspectRatio="none"
      role="img"
      :aria-label="t('radar.ind_rsi')"
    >
      <line :x1="pad" :x2="plotRight" y1="22" y2="22" stroke="rgb(var(--color-text-subtle))" stroke-dasharray="3 3" />
      <line :x1="pad" :x2="plotRight" y1="50" y2="50" stroke="rgb(var(--color-text-subtle))" stroke-dasharray="3 3" />
      <path :d="rsiPath" fill="none" stroke="rgb(var(--color-accent))" stroke-width="1.5" />
    </svg>
    <svg
      v-if="!loading && points.length && showDrawdown && ddPath"
      class="yf-chart-pane"
      :viewBox="paneViewBox"
      preserveAspectRatio="none"
      role="img"
      :aria-label="t('radar.ind_drawdown')"
    >
      <path :d="ddPath" fill="none" stroke="rgb(var(--color-danger))" stroke-width="1.5" />
    </svg>
    <div v-if="!loading && points.length && showSeasonality" class="yf-season">
      <div
        v-for="row in seasonality"
        :key="row.month"
        class="yf-season-cell"
        :title="row.avg == null ? '—' : `${row.avg.toFixed(2)}%`"
      >
        <span
          class="yf-season-bar"
          :style="{ height: `${seasonBar(row.avg)}px` }"
          :data-up="Number(row.avg) >= 0"
        ></span>
        <span class="yf-season-label">{{ monthLabels[row.month] }}</span>
      </div>
    </div>
    <p v-if="dd.drawdown < 0" class="yf-chart-hint">
      {{ t("radar.drawdown_active", { n: dd.drawdown.toFixed(1) }) }}
    </p>
    <div v-if="stats" class="yf-chart-readout">
      <div class="yf-chart-readout-delta" :data-up="selectionUp">{{ selectionDelta }}</div>
      <div class="yf-chart-readout-span">{{ selectionSpan }}</div>
      <div class="yf-chart-readout-range">
        {{ t("radar.chart_selection_high", { value: money(stats.high) }) }}
        ·
        {{ t("radar.chart_selection_low", { value: money(stats.low) }) }}
      </div>
      <div v-if="fibs.length" class="yf-chart-readout-range">
        {{ t("radar.ind_fib") }}
        {{ fibs.map((level) => `${Math.round(level.ratio * 100)}% ${money(level.value)}`).join(" · ") }}
      </div>
    </div>
    <div v-else-if="hoverLabel" class="yf-chart-tip">{{ hoverLabel }}</div>
    <p v-else class="yf-chart-hint">{{ t("radar.chart_drag_hint") }}</p>
  </div>
</template>
