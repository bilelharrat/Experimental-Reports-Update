<script setup>
// The company launcher. Clicking a company in the sidebar fills the content
// area with three large cards — the company's reports, its news, and the
// Research Desk — each previewing what it opens, so the choice is made
// looking at the material rather than at three menu labels. Everything shown
// is data the app already holds or a plain quotes read: nothing here asks
// for AI work.
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, unref, watch } from "vue";
import {
  AlertCircle,
  ArrowRight,
  ArrowUpRight,
  Building2,
  ChartLine,
  FileText,
  Newspaper,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import { newsAgeParts } from "../homeDesk.js";
import {
  closingPrices,
  companyFacts,
  companyHeadlines,
  companyPeople,
  companyReports,
  deskCoverage,
  formatPrice,
  normalizeReportStatus,
  reportLanguages,
  reportTitle,
  seriesChangePct,
  sparkAreaPaths,
  translatedField,
  useTickerNews,
} from "../companyLauncher.js";
import AiMark from "./AiMark.vue";
import CompanyFollowButton from "./CompanyFollowButton.vue";
import Monogram from "./Monogram.vue";

const props = defineProps({
  company: { type: Object, required: true },
  // The sidebar's list, which the news matching reads company names from.
  companies: { type: Array, default: () => [] },
  // Where the content column starts: the sidebar's width on a desktop.
  left: { type: Number, default: 0 },
});

// `go` carries a route location; the sidebar navigates and closes.
const emit = defineEmits(["close", "go"]);

const t = useT();
const workspaceNews = inject("workspaceNews", ref([]));
const workspaceResearch = inject("workspaceResearch", ref([]));
const workspaceLiveNews = inject("workspaceLiveNews", ref([]));
const openReportCustomizer = inject("openReportCustomizer", () => {});

const rootEl = ref(null);
const lang = computed(() => appLanguage.value || "en");
const companyId = computed(() => String(props.company?.id || ""));
const ticker = computed(() => String(props.company?.ticker || "").trim().toUpperCase());

const SPARK_RANGE = "6mo";
const SPARK_W = 240;
const SPARK_H = 64;

// ---- header ---------------------------------------------------------------

const industry = computed(
  () =>
    translatedField(props.company, "industry", lang.value) ||
    translatedField(props.company, "sector", lang.value) ||
    "",
);
const blurb = computed(() =>
  String(translatedField(props.company, "description", lang.value) || "").trim(),
);

const statusLabel = computed(() => {
  const company = props.company || {};
  const status = String(company.status || company.company_type || "").toLowerCase();
  if (status === "subsidiary") {
    return company.parent_company
      ? t("launcher.subsidiary_of", { name: company.parent_company })
      : t("launcher.subsidiary");
  }
  if (status === "public") return t("sidebar.public_equity");
  if (status === "private") return t("sidebar.private_company");
  return "";
});

const quote = ref(null);
const chartValues = ref([]);
let quoteRequest = 0;

function loadQuote() {
  const id = ++quoteRequest;
  quote.value = null;
  chartValues.value = [];
  const symbol = ticker.value;
  if (!symbol) return;
  api
    .liveQuotes([symbol])
    .then((payload) => {
      if (id === quoteRequest) quote.value = payload?.quotes?.[symbol] || null;
    })
    .catch(() => {});
  api
    .quoteChart(symbol, SPARK_RANGE)
    .then((payload) => {
      if (id === quoteRequest) chartValues.value = closingPrices(payload?.points);
    })
    .catch(() => {});
}

watch(ticker, loadQuote, { immediate: true });

const listing = computed(() => {
  const exchange = String(quote.value?.exchange || props.company?.exchange || "").trim();
  if (!ticker.value) return "";
  return exchange ? `${exchange} · ${ticker.value}` : ticker.value;
});
const price = computed(() =>
  quote.value ? formatPrice(quote.value.last_price, quote.value.currency) : "",
);
const dayPct = computed(() => {
  const pct = Number(quote.value?.change_pct_1d);
  return Number.isFinite(pct) ? pct : null;
});
const spark = computed(() => sparkAreaPaths(chartValues.value, { width: SPARK_W, height: SPARK_H }));
const sparkPct = computed(() => seriesChangePct(chartValues.value));

function signedPct(value) {
  if (value == null) return "";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

// ---- reports --------------------------------------------------------------

const REPORT_PREVIEW = 6;
const allReports = ref([]);
const reportsState = ref("loading");
let reportsRequest = 0;

async function loadReports() {
  const id = ++reportsRequest;
  reportsState.value = "loading";
  try {
    const list = await api.listReports();
    if (id !== reportsRequest) return;
    allReports.value = Array.isArray(list) ? list : [];
    reportsState.value = "ready";
  } catch {
    if (id === reportsRequest) reportsState.value = "error";
  }
}

const reports = computed(() => companyReports(allReports.value, companyId.value));
const reportPreview = computed(() => reports.value.slice(0, REPORT_PREVIEW));
const reportsMore = computed(() => Math.max(0, reports.value.length - REPORT_PREVIEW));

const reportsSubtitle = computed(() => {
  if (reportsState.value === "loading") return t("common.loading");
  const count = reports.value.length;
  if (count === 1) return t("launcher.reports_count_one");
  return count ? t("launcher.reports_count", { count }) : t("launcher.reports_hint");
});

const STATUS_LABEL_KEYS = {
  complete: "reports.status_complete",
  running: "reports.status_running",
  needs_attention: "reports.status_needs_attention",
  failed: "reports.status_failed",
};

function reportStatus(report) {
  return normalizeReportStatus(report?.status);
}

function reportDate(report) {
  const stamp = Date.parse(report?.created_at || "");
  if (!Number.isFinite(stamp)) return "";
  return new Date(stamp).toLocaleDateString(lang.value === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ---- news -----------------------------------------------------------------

const NEWS_PREVIEW = 6;
const ownLive = useTickerNews(ticker);
const headlines = computed(() =>
  companyHeadlines({
    feed: [...(unref(workspaceNews) || []), ...(unref(workspaceResearch) || [])],
    companies: props.companies,
    live: [...ownLive.value, ...(unref(workspaceLiveNews) || [])],
    companyId: companyId.value,
  }),
);
const newsPreview = computed(() => headlines.value.slice(0, NEWS_PREVIEW));

const newsSubtitle = computed(() => {
  const count = headlines.value.length;
  if (count === 1) return t("launcher.news_count_one");
  return count ? t("launcher.news_count", { count }) : t("launcher.news_hint");
});

function storyMeta(row) {
  const age = newsAgeParts(row?.ts);
  let when = "";
  if (age?.unit === "now") when = t("home.cache_just_now");
  else if (age?.unit === "minutes") when = t("home.cache_minutes_ago", { n: age.n });
  else if (age?.unit === "hours") when = t("home.cache_hours_ago", { n: age.n });
  else if (age?.unit === "days") when = t("home.cache_days_ago", { n: age.n });
  return [row?.source, when].filter(Boolean).join(" · ");
}

// ---- research desk --------------------------------------------------------

const FACT_LABEL_KEYS = {
  market_cap: "launcher.fact_market_cap",
  pe: "launcher.fact_pe",
  range: "launcher.fact_range",
  dividend: "launcher.fact_dividend",
  funding: "launcher.fact_funding",
  founded: "launcher.fact_founded",
  hq: "launcher.fact_hq",
  employees: "launcher.fact_employees",
  round: "launcher.fact_round",
  eps: "launcher.fact_eps",
  volume: "launcher.fact_volume",
  day_range: "launcher.fact_day_range",
  beta: "launcher.fact_beta",
};

const COVERAGE_LABEL_KEYS = {
  products: "launcher.coverage_products",
  competitors: "launcher.coverage_competitors",
  people: "launcher.coverage_people",
  contracts: "launcher.coverage_contracts",
  investors: "launcher.coverage_investors",
};

const facts = computed(() => companyFacts(props.company, quote.value));
const coverage = computed(() => deskCoverage(props.company));
const people = computed(() => companyPeople(props.company));
const milestone = computed(() => {
  const row = props.company?.highlight_2026;
  const headline = String(row?.headline || "").trim();
  return headline ? { headline, date: String(row?.date || "") } : null;
});
const deskIsEmpty = computed(
  () => !facts.value.length && !people.value.length && !milestone.value && !coverage.value.length,
);

function factLabel(fact) {
  return fact.key === "metric" ? fact.label : t(FACT_LABEL_KEYS[fact.key]);
}

// ---- navigation -----------------------------------------------------------

function destination(kind, extra = {}) {
  const id = companyId.value;
  if (kind === "reports") return { name: "reports", query: { company: id, ...extra } };
  if (kind === "news") return { name: "news-desk", query: { company: id, ...extra } };
  if (kind === "market") return { name: "market-radar", query: { ticker: ticker.value } };
  return { name: "research", params: { companyId: id } };
}

function go(kind, extra) {
  emit("go", destination(kind, extra), kind);
}

function openReport(report) {
  go("reports", { id: report.id });
}

function openStory(row) {
  go("news", { story: row.id });
}

function generateReport() {
  const id = companyId.value;
  emit("close");
  openReportCustomizer(id);
}

// A click on a card's open space opens it; its rows and buttons are their
// own targets.
function onCardClick(event, kind) {
  if (event.target?.closest?.("button, a")) return;
  go(kind);
}

// The glass's specular highlight follows the pointer across the pane.
function onCardPointer(event) {
  const card = event.currentTarget;
  const rect = card.getBoundingClientRect();
  card.style.setProperty("--mx", `${Math.round(event.clientX - rect.left)}px`);
  card.style.setProperty("--my", `${Math.round(event.clientY - rect.top)}px`);
}

// ---- keyboard -------------------------------------------------------------

const KEY_KINDS = { 1: "reports", 2: "news", 3: "desk" };

function inOtherDialog(target) {
  const dialog = target?.closest?.('[role="dialog"], [aria-modal="true"]');
  return Boolean(dialog && dialog !== rootEl.value && !rootEl.value?.contains(dialog));
}

// Registered on window in the capture phase so Escape closes the launcher
// before the app's own Escape handling (which would also shut Warren).
function onKeydown(event) {
  const target = event.target;
  if (inOtherDialog(target)) return;
  if (event.key === "Escape") {
    event.stopPropagation();
    event.preventDefault();
    emit("close", { restoreFocus: true });
    return;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  if (target?.closest?.("input, textarea, select, [contenteditable='true']")) return;
  const kind = KEY_KINDS[event.key];
  if (kind) {
    event.preventDefault();
    go(kind);
    return;
  }
  if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
  const root = rootEl.value;
  if (!root || !root.contains(document.activeElement)) return;
  const ctas = Array.from(root.querySelectorAll(".launcher-cta"));
  if (!ctas.length) return;
  event.preventDefault();
  const at = ctas.indexOf(document.activeElement);
  const step = event.key === "ArrowRight" ? 1 : -1;
  const next = at < 0 ? (step > 0 ? 0 : ctas.length - 1) : (at + step + ctas.length) % ctas.length;
  ctas[next].focus();
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown, true);
  loadReports();
  nextTick(() => rootEl.value?.focus({ preventScroll: true }));
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown, true);
});
</script>

<template>
  <div
    ref="rootEl"
    class="company-launcher"
    role="dialog"
    tabindex="-1"
    :aria-label="t('launcher.label', { name: company.name })"
    :style="{ left: `${left}px` }"
    data-testid="company-launcher"
  >
    <div class="launcher-scroll" @click.self="emit('close', { restoreFocus: true })">
    <Transition name="launcher-swap" mode="out-in">
      <div
        :key="companyId"
        class="company-launcher-inner"
        @click.self="emit('close', { restoreFocus: true })"
      >
        <header class="launcher-head">
          <span class="launcher-logo">
            <Monogram :company="company" :size="64" tinted />
          </span>
          <div class="launcher-head-main">
            <div class="launcher-eyebrow">
              <span v-if="statusLabel" class="launcher-status">{{ statusLabel }}</span>
              <!-- The ticker, like the price beside it, opens the stock on the
                   Market desk. -->
              <button
                v-if="listing"
                type="button"
                class="launcher-ticker focus-ring"
                :aria-label="t('launcher.open_market', { ticker })"
                :title="t('launcher.open_market', { ticker })"
                data-testid="launcher-ticker"
                @click="go('market')"
              >
                <ChartLine class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span class="mono-data">{{ listing }}</span>
              </button>
              <span v-if="industry" class="truncate">{{ industry }}</span>
            </div>
            <h2 class="launcher-title" data-testid="launcher-title">{{ company.name }}</h2>
            <p v-if="blurb" class="launcher-blurb">{{ blurb }}</p>
          </div>

          <button
            v-if="price"
            type="button"
            class="launcher-quote focus-ring"
            :aria-label="t('launcher.open_market', { ticker })"
            :title="t('launcher.open_market', { ticker })"
            data-testid="launcher-quote"
            @click="go('market')"
          >
            <div class="flex items-center justify-end gap-2">
              <span class="launcher-price mono-data">{{ price }}</span>
              <span v-if="dayPct != null" class="price-pill" :data-up="dayPct >= 0 ? 'true' : 'false'">
                {{ signedPct(dayPct) }}
              </span>
            </div>
            <svg
              v-if="spark.line"
              class="launcher-spark"
              :data-up="(sparkPct ?? 0) >= 0 ? 'true' : 'false'"
              :viewBox="`0 0 ${SPARK_W} ${SPARK_H}`"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <defs>
                <linearGradient id="launcher-spark-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="currentColor" stop-opacity="0.24" />
                  <stop offset="100%" stop-color="currentColor" stop-opacity="0" />
                </linearGradient>
              </defs>
              <path :d="spark.area" fill="url(#launcher-spark-fill)" />
              <path
                :d="spark.line"
                fill="none"
                stroke="currentColor"
                stroke-width="1.75"
                stroke-linecap="round"
                stroke-linejoin="round"
                vector-effect="non-scaling-stroke"
              />
            </svg>
            <div class="launcher-quote-sub">
              <span class="launcher-quote-open">
                {{ t("launcher.market") }}
                <ArrowUpRight class="h-3 w-3" aria-hidden="true" />
              </span>
              <span class="flex gap-1.5">
                <span>{{ t("launcher.today") }}</span>
                <template v-if="sparkPct != null">
                  <span aria-hidden="true">·</span>
                  <span>{{ t("launcher.six_months", { change: signedPct(sparkPct) }) }}</span>
                </template>
              </span>
            </div>
          </button>

          <div class="launcher-head-actions glass-capsule relative">
            <CompanyFollowButton :company-id="company.id" size="md" />
            <button
              type="button"
              class="icon-btn"
              :aria-label="t('launcher.close')"
              :title="t('launcher.close')"
              data-testid="launcher-close"
              @click="emit('close', { restoreFocus: true })"
            >
              <X class="h-[18px] w-[18px]" />
            </button>
          </div>
        </header>

        <div class="launcher-grid">
          <!-- Reports -->
          <section
            class="launcher-card"
            data-tone="reports"
            style="--i: 0"
            data-testid="launcher-reports"
            @click="onCardClick($event, 'reports')"
            @pointermove="onCardPointer"
          >
            <div class="launcher-card-head">
              <span class="launcher-card-icon"><FileText class="h-[22px] w-[22px]" /></span>
              <div class="min-w-0 flex-1">
                <h3 class="launcher-card-title">{{ t("launcher.reports") }}</h3>
                <p class="launcher-card-sub">{{ reportsSubtitle }}</p>
              </div>
              <span class="kbd max-lg:hidden" aria-hidden="true">1</span>
            </div>

            <div class="launcher-card-body">
              <div v-if="reportsState === 'loading'" class="launcher-skeleton" aria-hidden="true">
                <span v-for="n in 3" :key="n" />
              </div>
              <div v-else-if="reportsState === 'error'" class="launcher-empty">
                <span class="launcher-empty-icon" data-danger="true"><AlertCircle class="h-6 w-6" /></span>
                <p class="launcher-empty-title">{{ t("launcher.reports_error") }}</p>
                <button type="button" class="btn-bordered btn-sm focus-ring" @click="loadReports">
                  {{ t("common.retry") }}
                </button>
              </div>
              <ul v-else-if="reportPreview.length" class="launcher-list">
                <li v-for="report in reportPreview" :key="report.id">
                  <button
                    type="button"
                    class="launcher-row focus-ring"
                    data-testid="launcher-report"
                    @click="openReport(report)"
                  >
                    <span class="launcher-row-mark"><FileText class="h-4 w-4" /></span>
                    <span class="min-w-0 flex-1">
                      <span class="launcher-row-title">{{ reportTitle(report) }}</span>
                      <span class="launcher-row-meta">
                        <span class="launcher-status-dot" :data-status="reportStatus(report)" />
                        <span>{{ t(STATUS_LABEL_KEYS[reportStatus(report)]) }}</span>
                        <span v-if="reportDate(report)" aria-hidden="true">·</span>
                        <span class="tabular">{{ reportDate(report) }}</span>
                        <span v-for="code in reportLanguages(report)" :key="code" class="launcher-lang">{{ code }}</span>
                      </span>
                    </span>
                  </button>
                </li>
                <li v-if="reportsMore" class="launcher-more">
                  {{ t("launcher.more", { count: reportsMore }) }}
                </li>
              </ul>
              <div v-else class="launcher-empty">
                <span class="launcher-empty-icon"><FileText class="h-6 w-6" /></span>
                <p class="launcher-empty-title">{{ t("launcher.reports_empty", { name: company.name }) }}</p>
                <p class="launcher-empty-desc">{{ t("launcher.reports_empty_desc") }}</p>
                <button
                  type="button"
                  class="btn-tinted btn-sm focus-ring"
                  data-testid="launcher-generate"
                  @click="generateReport"
                >
                  <AiMark class="h-3.5 w-3.5 shrink-0" />
                  {{ t("memo.generate_report") }}
                </button>
              </div>
            </div>

            <div class="launcher-card-foot">
              <button
                type="button"
                class="launcher-cta focus-ring"
                data-testid="launcher-open-reports"
                @click="go('reports')"
              >
                <span>{{ t("launcher.open_reports") }}</span>
                <ArrowRight class="launcher-cta-arrow h-4 w-4" />
              </button>
            </div>
          </section>

          <!-- News -->
          <section
            class="launcher-card"
            data-tone="news"
            style="--i: 1"
            data-testid="launcher-news"
            @click="onCardClick($event, 'news')"
            @pointermove="onCardPointer"
          >
            <div class="launcher-card-head">
              <span class="launcher-card-icon"><Newspaper class="h-[22px] w-[22px]" /></span>
              <div class="min-w-0 flex-1">
                <h3 class="launcher-card-title">{{ t("launcher.news") }}</h3>
                <p class="launcher-card-sub">{{ newsSubtitle }}</p>
              </div>
              <span class="kbd max-lg:hidden" aria-hidden="true">2</span>
            </div>

            <div class="launcher-card-body">
              <ul v-if="newsPreview.length" class="launcher-list">
                <li v-for="(row, index) in newsPreview" :key="row.id">
                  <button
                    type="button"
                    class="launcher-row launcher-story focus-ring"
                    :data-lead="index === 0 ? 'true' : 'false'"
                    data-testid="launcher-story"
                    @click="openStory(row)"
                  >
                    <span class="min-w-0 flex-1">
                      <span v-if="storyMeta(row)" class="launcher-story-meta">{{ storyMeta(row) }}</span>
                      <span class="launcher-story-title">{{ row.title }}</span>
                      <span v-if="index === 0 && row.summary" class="launcher-story-summary">{{ row.summary }}</span>
                    </span>
                  </button>
                </li>
              </ul>
              <div v-else class="launcher-empty">
                <span class="launcher-empty-icon"><Newspaper class="h-6 w-6" /></span>
                <p class="launcher-empty-title">{{ t("launcher.news_empty", { name: company.name }) }}</p>
                <p class="launcher-empty-desc">{{ t("launcher.news_empty_desc") }}</p>
              </div>
            </div>

            <div class="launcher-card-foot">
              <button
                type="button"
                class="launcher-cta focus-ring"
                data-testid="launcher-open-news"
                @click="go('news')"
              >
                <span>{{ t("launcher.open_news") }}</span>
                <ArrowRight class="launcher-cta-arrow h-4 w-4" />
              </button>
            </div>
          </section>

          <!-- Research Desk -->
          <section
            class="launcher-card"
            data-tone="desk"
            style="--i: 2"
            data-testid="launcher-desk"
            @click="onCardClick($event, 'desk')"
            @pointermove="onCardPointer"
          >
            <div class="launcher-card-head">
              <span class="launcher-card-icon"><Building2 class="h-[22px] w-[22px]" /></span>
              <div class="min-w-0 flex-1">
                <h3 class="launcher-card-title">{{ t("launcher.desk") }}</h3>
                <p class="launcher-card-sub">{{ t("launcher.desk_hint") }}</p>
              </div>
              <span class="kbd max-lg:hidden" aria-hidden="true">3</span>
            </div>

            <div class="launcher-card-body">
              <div v-if="deskIsEmpty" class="launcher-empty">
                <span class="launcher-empty-icon"><Building2 class="h-6 w-6" /></span>
                <p class="launcher-empty-title">{{ t("launcher.desk_empty") }}</p>
                <p class="launcher-empty-desc">{{ t("launcher.desk_empty_desc", { name: company.name }) }}</p>
              </div>
              <template v-else>
                <dl v-if="facts.length" class="launcher-facts">
                  <div v-for="fact in facts" :key="`${fact.key}:${fact.label}`" class="launcher-fact">
                    <dt>{{ factLabel(fact) }}</dt>
                    <dd class="mono-data">{{ fact.value }}</dd>
                  </div>
                </dl>
                <div v-if="coverage.length" class="launcher-section">
                  <h4 class="launcher-section-label">{{ t("launcher.on_file") }}</h4>
                  <ul class="launcher-coverage">
                    <li v-for="row in coverage" :key="row.key">
                      <span>{{ t(COVERAGE_LABEL_KEYS[row.key]) }}</span>
                      <span class="mono-data">{{ row.count }}</span>
                    </li>
                  </ul>
                </div>
                <div v-if="people.length" class="launcher-section">
                  <h4 class="launcher-section-label">{{ t("launcher.people") }}</h4>
                  <ul class="space-y-2">
                    <li v-for="person in people" :key="person.name" class="launcher-person">
                      <Monogram :name="person.name" :size="28" tinted round />
                      <span class="min-w-0 flex-1 leading-tight">
                        <span class="block truncate text-callout font-medium text-ink-primary">{{ person.name }}</span>
                        <span v-if="person.role" class="block truncate text-footnote text-ink-muted">{{ person.role }}</span>
                      </span>
                    </li>
                  </ul>
                </div>
                <div v-if="milestone" class="launcher-section">
                  <h4 class="launcher-section-label">{{ t("launcher.milestone") }}</h4>
                  <p class="text-callout leading-snug text-ink-secondary">{{ milestone.headline }}</p>
                  <p v-if="milestone.date" class="mt-1 text-caption1 text-ink-muted tabular">{{ milestone.date }}</p>
                </div>
              </template>
            </div>

            <div class="launcher-card-foot">
              <button
                type="button"
                class="launcher-cta focus-ring"
                data-testid="launcher-open-desk"
                @click="go('desk')"
              >
                <span>{{ t("launcher.open_desk") }}</span>
                <ArrowRight class="launcher-cta-arrow h-4 w-4" />
              </button>
            </div>
          </section>
        </div>
      </div>
    </Transition>
    </div>
  </div>
</template>
