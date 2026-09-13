<script setup>
import { computed, inject, onMounted, onUnmounted, ref, unref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Loader2, Maximize2, Minimize2, Newspaper, Search, Star, TrendingDown, TrendingUp } from "lucide-vue-next";
import { api } from "../api.js";
import CompanyFollowButton from "../components/CompanyFollowButton.vue";
import QuoteChart from "../components/QuoteChart.vue";
import QuoteSparkline from "../components/QuoteSparkline.vue";
import QuoteWorkspace from "../components/QuoteWorkspace.vue";
import { formatCompactNumber } from "../formatters.js";
import {
  CHART_RANGES,
  assembleDeskNews,
  filingSnips,
  filterScreenerRows,
  indexQuoteCards,
  lookupQuoteMatches,
  MARKET_INDEX_TICKERS,
  WEI_TICKERS,
  quoteBoardRows,
  quoteGainers,
  quoteLosers,
  quoteMostActive,
  rankDeskNews,
} from "../homeDesk.js";
import { lastPriceLabel, publicTickers, quoteStaleness, signedChange } from "../liveTicker.js";
import { bookBetaRisk, bookConcentration, bookPnl, loadBookLots } from "../marketBook.js";
import {
  breadthStrip,
  earningsCountdown,
  enrichScreenerRow,
  gapSplit,
  headlineReaction,
  macroWeekGrid,
  pairSpreadSeries,
  researchHitsForTicker,
  returnLadder,
  taggingFilingSnips,
} from "../marketAnalytics.js";
import { marketRadarItems, radarAge, radarRoute } from "../marketRadar.js";
import {
  deleteDesk,
  clearAlertHistory,
  downloadIcs,
  edgarLinks,
  earningsStrip,
  findDesk,
  freshAlerts,
  heatTone,
  loadAlertHistory,
  loadAlertMutes,
  loadDesks,
  loadLastDeskId,
  loadRecentTickers,
  loadTickerNote,
  loadWatchColumns,
  muteAlert,
  notifyAlerts,
  pushRecentTicker,
  requestAlertPermission,
  rrgLayout,
  rrgPoints,
  rrgTrails,
  saveDesk,
  saveTickerNote,
  saveWatchColumns,
  loadDeskLayout,
  saveDeskLayout,
  sectorHeatmap,
  setLastDeskId,
  toggleWatchColumn,
  visibleAlerts,
  volumeRatio,
  vsSpyDay,
  WATCH_COLUMN_IDS,
} from "../marketDesk.js";
import {
  deleteSavedScreen,
  findSavedScreen,
  hasScreenQuery,
  loadSavedScreens,
  saveScreen,
  screenFiltersFromQuery,
  screenFiltersToQuery,
} from "../marketScreens.js";
import {
  ensureDefaultAlertRules,
  evaluateAlertRules,
  groupPinnedTickers,
  isPinnedTicker,
  loadAlertRules,
  loadHpCompare,
  loadPinGroups,
  loadPinnedTickers,
  mergeAlerts,
  pinGroupFor,
  saveHpCompare,
  setPinGroup,
  toggleHpCompare,
  togglePinnedTicker,
  upsertAlertRule,
  WATCH_GROUPS,
  watchlistAlerts,
} from "../marketWatchlist.js";
import { betaVs } from "../quoteChart.js";
import { appLanguage, trackedCompanyIds } from "../state.js";
import { useLiveQuotes } from "../useLiveQuotes.js";
import { useT } from "../i18n.js";

const t = useT();
const router = useRouter();
const route = useRoute();
const openCopilot = inject("openCopilot", null);

const news = inject("workspaceNews", ref([]));
const research = inject("workspaceResearch", ref([]));
const liveNews = inject("workspaceLiveNews", ref([]));
const companies = inject("workspaceCompanies", ref([]));
const loadingFeed = inject("workspaceLoading", ref(false));

const tab = ref("gainers");
const selectedTicker = ref(String(route.query.ticker || "SPY").toUpperCase());
const secondaryTicker = ref("");
const secondaryChart = ref(null);
const secondaryWorkspace = ref(null);
const secondaryLoading = ref(false);
const extraTickers = ref([]);
const recentTickers = ref(loadRecentTickers());
const query = ref("");
const showSuggestions = ref(false);
const remoteMatches = ref([]);
const chartRange = ref("1d");
const chart = ref(null);
const chartLoading = ref(false);
const chartError = ref("");
const workspace = ref(null);
const workspaceTab = ref("profile");
const workspaceLoading = ref(false);
const peers = ref(null);
const peersLoading = ref(false);
const calendar = ref({ events: [] });
const calendarLoading = ref(false);
const calendarFilter = ref("all");
const focusPanel = ref(String(route.query.panel || ""));
const screeners = ref({ gainers: [], losers: [], active: [], universe: [], sectors: [] });
const screenerSector = ref("");
const screenerCap = ref("");
const screenerMinChange = ref("");
const screenerMinVolume = ref("");
const screenerQuery = ref("");
const savedScreens = ref(loadSavedScreens());
const screenNameDraft = ref("");
const savedDesks = ref(loadDesks());
const deskNameDraft = ref("");
const pinnedTickers = ref(loadPinnedTickers());
const pinGroups = ref(loadPinGroups());
const watchGroupFilter = ref("all");
const hpCompare = ref(loadHpCompare());
const hpSeries = ref([]);
const hpInput = ref("");
const alertRules = ref(loadAlertRules());
const alertMutes = ref(loadAlertMutes());
const watchColumns = ref(loadWatchColumns());
const returnCache = ref({});
const chartPointsCache = ref({});
const newsScope = ref("all");
const tickerNote = ref(loadTickerNote(selectedTicker.value));
const priceAlertLevel = ref("");
const priceAlertDir = ref("above");
const smaAlertWindow = ref("50");
const corrBench = ref("SPY");
const twoUp = ref(Boolean(route.query.two));
const deskExpanded = ref(
  route.query.wide === "1" || route.query.wide === "true" || loadDeskLayout().expanded,
);
const pairMode = ref("diff");
const calendarView = ref(route.query.week === "0" ? "list" : "week");
const alertHistory = ref(loadAlertHistory());
const bookLots = ref(loadBookLots());
const showDeskSave = ref(false);
const showAlertRules = ref(false);
const showAlertHistory = ref(false);
const showKeyHelp = ref(false);
const showPair = ref(false);
const showAllStats = ref(false);
const showCompMore = ref(false);
const shareToast = ref("");
const breadthHistory = ref([]);
const groupMenuTicker = ref("");
const notifyEnabled = ref(
  typeof Notification !== "undefined" && Notification.permission === "granted",
);
const pulse = ref(null);
const pulseLoading = ref(false);
const pulseError = ref("");
const serverAlerts = ref([]);
const ledgerEntries = ref([]);
const signalToast = ref("");
let searchTimer = 0;
let signalToastTimer = 0;

const ALERTS_SEEN_KEY = "bsh.marketAlertsSeenAt";

const companyList = computed(() => unref(companies) || []);
const trackedCompanies = computed(() =>
  companyList.value.filter((company) =>
    trackedCompanyIds.value.has(String(company.id)),
  ),
);
const suggestions = computed(() => {
  const local = lookupQuoteMatches(query.value, companyList.value);
  const seen = new Set(local.map((row) => row.ticker).filter(Boolean));
  const merged = [...local];
  for (const row of remoteMatches.value) {
    const ticker = String(row?.ticker || "").trim().toUpperCase();
    if (!ticker || seen.has(ticker)) continue;
    seen.add(ticker);
    merged.push({
      ticker,
      name: row.name || ticker,
      companyId: null,
      kind: "ticker",
    });
    if (merged.length >= 8) break;
  }
  return merged;
});
const boardTickers = computed(() => {
  const seen = new Set();
  const tickers = [];
  const push = (ticker) => {
    const symbol = String(ticker || "").trim().toUpperCase();
    if (!symbol || seen.has(symbol)) return;
    seen.add(symbol);
    tickers.push(symbol);
  };
  for (const def of MARKET_INDEX_TICKERS) push(def.ticker);
  for (const ticker of extraTickers.value) push(ticker);
  for (const ticker of pinnedTickers.value) push(ticker);
  for (const ticker of hpCompare.value) push(ticker);
  for (const ticker of publicTickers(trackedCompanies.value)) push(ticker);
  if (selectedTicker.value) push(selectedTicker.value);
  for (const ticker of publicTickers(companyList.value)) push(ticker);
  return tickers.slice(0, 56);
});

const { quotes } = useLiveQuotes(boardTickers);
const indexes = computed(() => {
  const defs = MARKET_INDEX_TICKERS.filter((def) => WEI_TICKERS.includes(def.ticker));
  return indexQuoteCards(quotes.value, defs).map((card) => {
    const points = chartPointsCache.value[card.ticker] || [];
    const spark = points.slice(-42).map((point) => Number(point?.close)).filter(Number.isFinite);
    return { ...card, spark };
  });
});
const boardRows = computed(() =>
  quoteBoardRows(quotes.value, companyList.value).filter(
    (row) => !MARKET_INDEX_TICKERS.some((def) => def.ticker === row.ticker),
  ),
);
const gainers = computed(() => quoteGainers(boardRows.value, 12));
const losers = computed(() => quoteLosers(boardRows.value, 12));
const active = computed(() => quoteMostActive(boardRows.value, 12));
const watchlist = computed(() => {
  const byTicker = new Map(boardRows.value.map((row) => [row.ticker, row]));
  const rows = [];
  const seen = new Set();
  const pushTicker = (ticker, company = null) => {
    const symbol = String(ticker || "").trim().toUpperCase();
    if (!symbol || seen.has(symbol)) return;
    seen.add(symbol);
    const quote = quotes.value[symbol] || {};
    const board = byTicker.get(symbol);
    rows.push({
      ticker: symbol,
      name: company?.name || board?.name || quote.name || symbol,
      last: board?.last ?? quote.last_price ?? null,
      change: board?.change ?? quote.change_pct_1d ?? null,
      volume: board?.volume ?? quote.volume ?? null,
      currency: board?.currency || quote.currency || "USD",
      companyId: company?.id || board?.companyId || null,
      weekHigh: quote.fifty_two_week_high ?? null,
      weekLow: quote.fifty_two_week_low ?? null,
      avgVolume: quote.avg_volume ?? null,
      ytd: returnCache.value[symbol]?.ytd ?? null,
      vsSpy1y: returnCache.value[symbol]?.vsSpy1y ?? null,
      group: pinGroupFor(symbol, pinGroups.value),
      pinned: true,
    });
  };
  for (const company of trackedCompanies.value) {
    pushTicker(company.ticker, company);
  }
  for (const ticker of pinnedTickers.value) {
    const company = companyList.value.find(
      (row) => String(row.ticker || "").trim().toUpperCase() === ticker,
    );
    pushTicker(ticker, company || null);
  }
  const filtered =
    watchGroupFilter.value === "all"
      ? rows
      : rows.filter((row) => row.group === watchGroupFilter.value);
  return filtered.sort((a, b) => {
    const g = String(a.group).localeCompare(String(b.group));
    return g || a.ticker.localeCompare(b.ticker);
  });
});
const watchGroups = computed(() =>
  groupPinnedTickers(
    [...new Set([...pinnedTickers.value, ...publicTickers(trackedCompanies.value)])],
    pinGroups.value,
  ),
);
const earningsByTicker = computed(() => {
  const map = {};
  for (const event of calendar.value?.events || []) {
    if (event?.kind !== "earnings" || !event.ticker || !event.date) continue;
    const ticker = String(event.ticker).toUpperCase();
    if (!map[ticker] || String(event.date) < map[ticker]) {
      map[ticker] = String(event.date).slice(0, 10);
    }
  }
  if (workspace.value?.earnings?.next_date && selectedTicker.value) {
    map[selectedTicker.value] = String(workspace.value.earnings.next_date).slice(0, 10);
  }
  return map;
});
const rawAlerts = computed(() =>
  mergeAlerts(
    watchlistAlerts(watchlist.value),
    evaluateAlertRules(watchlist.value, alertRules.value, {
      earningsByTicker: earningsByTicker.value,
      chartPointsByTicker: chartPointsCache.value,
    }),
  ),
);
const alerts = computed(() => visibleAlerts(rawAlerts.value, alertMutes.value));
const bookLens = computed(() =>
  bookConcentration(trackedCompanies.value, quotes.value),
);
const spyChange = computed(() => Number(quotes.value.SPY?.change_pct_1d));
const heatRows = computed(() => sectorHeatmap(screeners.value.universe || []));
const earnStrip = computed(() => earningsStrip(workspace.value));
const filingLinks = computed(() => edgarLinks(selectedTicker.value));
const watchColSet = computed(() => new Set(watchColumns.value));
const boardGridStyle = computed(() => {
  const extra = watchColumns.value.length;
  return {
    gridTemplateColumns: `minmax(0, 1.6fr) ${Array.from({ length: extra }, () => "minmax(0, 0.75fr)").join(" ")}`,
  };
});
const calendarTickers = computed(() => {
  const tickers = watchlist.value.map((row) => row.ticker).filter(Boolean);
  if (selectedTicker.value && !tickers.includes(selectedTicker.value)) {
    tickers.unshift(selectedTicker.value);
  }
  return tickers.slice(0, 24);
});
const bookCatalystEvents = computed(() => {
  const rows = [];
  const seen = new Set();
  const push = (event) => {
    const key = `${event.kind}:${event.ticker || ""}:${event.date}:${event.title || ""}`;
    if (seen.has(key) || !event.date) return;
    seen.add(key);
    rows.push(event);
  };
  for (const company of trackedCompanies.value) {
    const ticker = String(company.ticker || "").trim().toUpperCase();
    const snap = company.trader_snapshot || {};
    const heat = snap.heat?.next_catalyst || company.heat?.next_catalyst;
    if (heat?.date) {
      push({
        ticker: ticker || null,
        name: company.name,
        date: String(heat.date).slice(0, 10),
        time: null,
        kind: "catalyst",
        title: heat.label || heat.title || "Catalyst",
        confirmed: true,
      });
    }
    for (const item of snap.catalysts || company.catalysts || []) {
      const date = String(item?.date || "").slice(0, 10);
      if (!date) continue;
      push({
        ticker: ticker || null,
        name: company.name,
        date,
        time: null,
        kind: "catalyst",
        title: item.title || item.label || item.type || "Catalyst",
        confirmed: true,
      });
    }
  }
  return rows;
});

const calendarFilters = computed(() => [
  { id: "all", label: t("radar.cal_all") },
  { id: "earnings", label: t("radar.cal_earnings") },
  { id: "dividend", label: t("radar.cal_dividends") },
  { id: "macro", label: t("radar.cal_macro") },
  { id: "catalyst", label: t("radar.cal_book") },
]);

const upcomingEvents = computed(() => {
  const merged = [...(calendar.value?.events || []), ...bookCatalystEvents.value];
  merged.sort((a, b) => String(a.date).localeCompare(String(b.date)));
  if (calendarFilter.value === "all") return merged.slice(0, 60);
  return merged.filter((row) => row.kind === calendarFilter.value).slice(0, 60);
});
const filteredScreener = computed(() =>
  filterScreenerRows(screeners.value.universe || [], {
    sector: screenerSector.value,
    cap: screenerCap.value,
    minChange: screenerMinChange.value === "" ? null : Number(screenerMinChange.value),
    minVolume: screenerMinVolume.value === "" ? null : Number(screenerMinVolume.value),
    query: screenerQuery.value,
    limit: 40,
  }),
);

const tableRows = computed(() => {
  if (tab.value === "losers") return losers.value;
  if (tab.value === "active") return active.value;
  if (tab.value === "watchlist") return watchlist.value;
  if (tab.value === "screener") {
    return filteredScreener.value.map((row) => ({
      ticker: row.ticker,
      name: row.name,
      last: row.last,
      change: row.change_pct,
      volume: row.volume,
      currency: "USD",
      companyId: null,
      sector: row.sector,
      marketCap: row.market_cap,
    }));
  }
  return gainers.value;
});

const selectedCompany = computed(() => {
  const ticker = selectedTicker.value;
  return (
    companyList.value.find(
      (row) => String(row.ticker || "").trim().toUpperCase() === ticker,
    ) || null
  );
});

const competitorTickers = computed(() => {
  const company = selectedCompany.value;
  if (!company) return [];
  const rows = [];
  for (const item of company.competitors || []) {
    if (typeof item === "string") continue;
    const ticker = String(item?.ticker || "").trim().toUpperCase();
    if (ticker) rows.push(ticker);
  }
  for (const item of company.competitor_cards || []) {
    const ticker = String(item?.ticker || "").trim().toUpperCase();
    if (ticker) rows.push(ticker);
  }
  return [...new Set(rows)].slice(0, 6);
});

const selected = computed(() => {
  const ticker = selectedTicker.value;
  const fromBoard = ticker
    ? boardRows.value.find((row) => row.ticker === ticker)
      || indexes.value.find((row) => row.ticker === ticker)
      || watchlist.value.find((row) => row.ticker === ticker)
    : null;
  const quote = ticker ? quotes.value[ticker] : null;
  const payload = chart.value?.ticker === ticker ? chart.value : null;
  if (!ticker && !fromBoard && !payload) {
    return tableRows.value[0] || boardRows.value[0] || indexes.value[0] || null;
  }
  const company = selectedCompany.value;
  return {
    ticker: ticker || fromBoard?.ticker || payload?.ticker,
    label: fromBoard?.label,
    name:
      fromBoard?.name
      || payload?.name
      || quote?.name
      || company?.name
      || ticker,
    companyId: fromBoard?.companyId || company?.id || null,
    last: payload?.last_price ?? fromBoard?.last ?? quote?.last_price ?? null,
    change: payload?.change_pct_1d ?? fromBoard?.change ?? quote?.change_pct_1d ?? null,
    changeAbs: payload?.change ?? null,
    currency: payload?.currency || fromBoard?.currency || quote?.currency || "USD",
    exchange: payload?.exchange || quote?.exchange || fromBoard?.exchange || "",
    previousClose: payload?.previous_close ?? quote?.previous_close ?? null,
    open: payload?.open ?? quote?.open ?? null,
    high: payload?.high ?? quote?.high ?? null,
    low: payload?.low ?? quote?.low ?? null,
    volume: payload?.volume ?? quote?.volume ?? fromBoard?.volume ?? null,
    avgVolume: payload?.avg_volume ?? quote?.avg_volume ?? null,
    marketCap: payload?.market_cap ?? quote?.market_cap ?? null,
    peRatio: payload?.pe_ratio ?? quote?.pe_ratio ?? null,
    eps: payload?.eps ?? quote?.eps ?? null,
    beta: payload?.beta ?? quote?.beta ?? null,
    dividendYield: payload?.dividend_yield ?? quote?.dividend_yield ?? null,
    dividend: payload?.dividend ?? quote?.dividend ?? null,
    weekHigh: payload?.fifty_two_week_high ?? quote?.fifty_two_week_high ?? null,
    weekLow: payload?.fifty_two_week_low ?? quote?.fifty_two_week_low ?? null,
    asOf: payload?.as_of || fromBoard?.asOf || quote?.as_of || null,
  };
});

const deskNews = computed(() =>
  assembleDeskNews({
    feed: [...(unref(news) || []), ...(unref(research) || [])],
    companies: companyList.value,
    live: unref(liveNews) || [],
  }),
);

const selectedHeadlines = computed(() => {
  const radar = marketRadarItems(unref(news) || [], unref(research) || [], 36);
  const fromDesk = deskNews.value.map((row) => ({
    id: row.id,
    title: row.title,
    summary: row.summary,
    captured_at: row.ts,
    companyIds: row.companyIds,
    category: row.category,
    source: row.source,
    url: row.url,
    ts: row.ts,
    title_zh: row.raw?.headline_zh || row.raw?.title_zh,
  }));
  const merged = [...fromDesk];
  const seen = new Set(merged.map((row) => row.id));
  for (const item of radar) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    merged.push({
      ...item,
      category: item.category || "",
      ts: item.captured_at,
    });
  }
  const bookIds = [...trackedCompanyIds.value].map(String);
  let rows = rankDeskNews(merged, {
    bookIds,
    ticker: selected.value?.ticker,
    name: selected.value?.name,
    lang: appLanguage.value,
    limit: 24,
  });
  if (newsScope.value === "filings") {
    rows = rows.filter((row) => row.category === "filings");
  } else if (newsScope.value === "book") {
    rows = rows.filter((row) => (row.companyIds || []).some((id) => bookIds.includes(String(id))));
  }
  return rows.slice(0, 12);
});

const selectedFilings = computed(() =>
  taggingFilingSnips(
    filingSnips(deskNews.value, {
      ticker: selected.value?.ticker,
      name: selected.value?.name,
      limit: 12,
    }),
    {
      ticker: selected.value?.ticker,
      name: selected.value?.name,
      limit: 8,
    },
  ),
);

const chartEvents = computed(() => {
  const past = (workspace.value?.earnings?.past || []).map((row) => ({
    date: row.reported,
    label: "E",
    kind: "earnings",
  }));
  const next = workspace.value?.earnings?.next_date
    ? [{ date: workspace.value.earnings.next_date, label: "E?", kind: "earnings" }]
    : [];
  const corporate = (chart.value?.events || []).map((row) => ({
    ...row,
    label: row.label || (row.kind === "split" ? "S" : row.kind === "dividend" ? "D" : "E"),
  }));
  // Research overlay: logged signal calls and matched research/memo items
  // become chart markers so price action lines up with the paper trail.
  const signals = ledgerEntries.value
    .filter((row) => String(row.ticker || "") === selectedTicker.value)
    .map((row) => ({
      date: String(row.recorded_at || "").slice(0, 10),
      label: row.direction === "bearish" ? "S↓" : row.direction === "bullish" ? "S↑" : "S",
      kind: "signal",
    }));
  const researchMarks = researchHits.value
    .filter((row) => row.ts)
    .slice(0, 6)
    .map((row) => ({
      date: String(row.ts).slice(0, 10),
      label: "R",
      kind: "research",
    }));
  return [...next, ...past, ...corporate, ...signals, ...researchMarks];
});

const gapStats = computed(() =>
  gapSplit({
    open: selected.value?.open ?? chart.value?.open,
    previousClose: selected.value?.previousClose ?? chart.value?.previous_close,
    last: selected.value?.last ?? chart.value?.last_price,
  }),
);

const ladder = computed(() => {
  const primary = peers.value?.primary || {};
  return returnLadder(chart.value?.points || [], {
    "1m": primary.ret_1m,
    ytd: primary.ret_ytd,
    "1y": primary.ret_1y,
  });
});
const visibleLadder = computed(() => {
  const longOk = ["1y", "5y", "max"].includes(chartRange.value);
  return ladder.value.filter((row) => row.id !== "3y" || longOk);
});

const breadth = computed(() =>
  breadthStrip(watchlist.value, chartPointsCache.value),
);

const researchHits = computed(() =>
  researchHitsForTicker({
    ticker: selected.value?.ticker,
    name: selected.value?.name,
    news: unref(news) || [],
    research: unref(research) || [],
    companies: companyList.value,
    limit: 8,
  }),
);

const weekGrid = computed(() => macroWeekGrid(upcomingEvents.value));

const pairPoints = computed(() => {
  const peer =
    (secondaryChart.value?.points?.length && secondaryChart.value.points) ||
    hpSeries.value.find((row) => row.ticker !== selectedTicker.value)?.points ||
    peers.value?.benchmark?.points ||
    [];
  return pairSpreadSeries(chart.value?.points || [], peer, { mode: pairMode.value });
});

const pairPeerLabel = computed(() => {
  if (deskBTicker.value) return deskBTicker.value;
  return hpCompare.value.find((ticker) => ticker !== selectedTicker.value) || "SPY";
});
const pairStats = computed(() => {
  const series = pairPoints.value;
  if (series.length < 5) return { last: null, z: null };
  const values = series.map((row) => Number(row.close)).filter(Number.isFinite);
  const last = values[values.length - 1];
  const mean = values.reduce((sum, n) => sum + n, 0) / values.length;
  const variance = values.reduce((sum, n) => sum + (n - mean) ** 2, 0) / values.length;
  const sigma = Math.sqrt(variance);
  return {
    last,
    z: sigma > 0 ? (last - mean) / sigma : null,
  };
});
const canShowPair = computed(() =>
  Boolean(
    showPair.value &&
      (hpCompare.value.some((ticker) => ticker !== selectedTicker.value) || deskBTicker.value) &&
      pairPoints.value.length,
  ),
);

const hasPairPeer = computed(
  () =>
    hpCompare.value.some((ticker) => ticker !== selectedTicker.value) || Boolean(deskBTicker.value),
);

const secondaryChartEvents = computed(() => {
  const past = (secondaryWorkspace.value?.earnings?.past || []).map((row) => ({
    date: row.reported,
    label: "E",
    kind: "earnings",
  }));
  const next = secondaryWorkspace.value?.earnings?.next_date
    ? [{ date: secondaryWorkspace.value.earnings.next_date, label: "E?", kind: "earnings" }]
    : [];
  const corporate = (secondaryChart.value?.events || []).map((row) => ({
    ...row,
    label: row.label || (row.kind === "split" ? "S" : row.kind === "dividend" ? "D" : "E"),
  }));
  return [...next, ...past, ...corporate];
});

const displayBoardRows = computed(() =>
  tab.value === "screener" ? enrichedScreenerRows.value : tableRows.value,
);

const bookRisk = computed(() => bookBetaRisk(bookLots.value, quotes.value));
const bookPnlView = computed(() => bookPnl(bookLots.value, quotes.value));
const selectedStaleness = computed(() => quoteStaleness(selected.value?.asOf));
const secondaryLadder = computed(() =>
  returnLadder(secondaryChart.value?.points || []).filter((row) =>
    ["1d", "1w", "1m", "ytd"].includes(row.id),
  ),
);
const enrichedScreenerRows = computed(() =>
  (tableRows.value || []).map((row) =>
    enrichScreenerRow(row, {
      chartPoints: chartPointsCache.value[row.ticker] || [],
      earningsDate: earningsByTicker.value[row.ticker],
    }),
  ),
);

const workspaceTabs = ["profile", "statistics", "financials", "analysis", "holders", "options", "history", "earnings"];

const peerSeries = computed(() => {
  const rows = [];
  const seen = new Set();
  const push = (ticker, points) => {
    const symbol = String(ticker || "").trim().toUpperCase();
    if (!symbol || !points?.length || seen.has(symbol)) return;
    if (symbol === selectedTicker.value) return;
    seen.add(symbol);
    rows.push({ ticker: symbol, points });
  };
  for (const series of hpSeries.value) {
    push(series.ticker, series.points);
  }
  if (peers.value?.benchmark?.points?.length) {
    push("SPY", peers.value.benchmark.points);
  }
  for (const row of peers.value?.peers || []) {
    if (row?.points?.length) push(row.ticker, row.points);
  }
  return rows.slice(0, 4);
});

const peerTable = computed(() => {
  if (!peers.value) return [];
  const rows = [peers.value.primary, peers.value.benchmark, ...(peers.value.peers || [])].filter(Boolean);
  const benchPoints =
    rows.find((row) => row.ticker === corrBench.value)?.points ||
    peers.value.benchmark?.points ||
    [];
  return rows.map((row) => {
    const stats = betaVs(row.points || [], benchPoints, 60);
    return {
      ...row,
      beta60: stats.beta,
      corr60: stats.corr,
    };
  });
});
const rrg = computed(() => rrgLayout(rrgPoints(peerTable.value)));
const rrgTrailLayout = computed(() => {
  const layout = rrg.value;
  const trails = rrgTrails(peerTable.value);
  const mid = layout.mid;
  const scale = layout.scale || 1;
  return trails.map((trail) => ({
    ticker: trail.ticker,
    d: trail.path
      .map((point, index) => {
        const x = mid + point.x * scale;
        const y = mid - point.y * scale;
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" "),
  }));
});
const secondarySeries = computed(() => {
  if (!secondaryChart.value?.points?.length) return [];
  return [{ ticker: secondaryTicker.value, points: secondaryChart.value.points }];
});
const deskBTicker = computed(() => {
  if (secondaryTicker.value) return secondaryTicker.value;
  return hpCompare.value.find((ticker) => ticker !== selectedTicker.value) || "";
});

const selectedPinned = computed(() => isPinnedTicker(selectedTicker.value, pinnedTickers.value));
const holderMixLabel = computed(() => {
  const mix =
    selectedCompany.value?.trader_snapshot?.heat?.holder_mix ||
    selectedCompany.value?.heat?.holder_mix ||
    "";
  return typeof mix === "string" ? mix : mix?.label || "";
});

const tabs = computed(() => [
  { id: "gainers", label: t("radar.tab_gainers"), count: gainers.value.length },
  { id: "losers", label: t("radar.tab_losers"), count: losers.value.length },
  { id: "active", label: t("radar.tab_active"), count: active.value.length },
  { id: "watchlist", label: t("radar.tab_watchlist"), count: watchlist.value.length },
  { id: "screener", label: t("radar.tab_screener"), count: filteredScreener.value.length },
]);

const rangeLabels = computed(() => ({
  "1d": t("radar.range_1d"),
  "5d": t("radar.range_5d"),
  "1mo": t("radar.range_1mo"),
  "6mo": t("radar.range_6mo"),
  ytd: t("radar.range_ytd"),
  "1y": t("radar.range_1y"),
  "5y": t("radar.range_5y"),
  max: t("radar.range_max"),
}));

const regime = computed(() => pulse.value?.sections?.market_regime || {});
const posture = computed(() => String(regime.value.posture || "empty"));
const postureLabel = computed(() => {
  const key = `home.desk_posture_${posture.value.replace("-", "_")}`;
  const label = t(key);
  return label === key ? posture.value : label;
});
const topSignal = computed(() => pulse.value?.summary?.top_signal || "");

const weekRangePct = computed(() => {
  const low = Number(selected.value?.weekLow);
  const high = Number(selected.value?.weekHigh);
  const last = Number(selected.value?.last);
  if (![low, high, last].every(Number.isFinite) || high <= low) return null;
  return Math.min(100, Math.max(0, ((last - low) / (high - low)) * 100));
});

const stats = computed(() => {
  const row = selected.value;
  if (!row) return [];
    const earn = workspace.value?.earnings;
  const summary = workspace.value?.summary || {};
  const yieldFromSummary = summary.yield || null;
  return [
    { label: t("radar.stat_prev"), value: money(row.previousClose, row.currency) },
    { label: t("radar.stat_open"), value: money(row.open, row.currency) },
    { label: t("radar.stat_high"), value: money(row.high, row.currency) },
    { label: t("radar.stat_low"), value: money(row.low, row.currency) },
    { label: t("radar.stat_volume"), value: compact(row.volume) },
    { label: t("radar.stat_avg_volume"), value: compact(row.avgVolume) },
    { label: t("radar.stat_mktcap"), value: money(row.marketCap, row.currency, true) },
    { label: t("radar.stat_pe"), value: number(row.peRatio) },
    { label: t("radar.stat_eps"), value: money(row.eps, row.currency) },
    { label: t("radar.stat_beta"), value: number(row.beta) },
    {
      label: t("radar.stat_div_amt"),
      value: summary.dividend || row.dividend || "—",
    },
    {
      label: t("radar.stat_div"),
      value:
        row.dividendYield != null
          ? percent(row.dividendYield)
          : yieldFromSummary || "—",
    },
    {
      label: t("radar.stat_exdiv"),
      value: summary.ex_dividend || "—",
    },
    { label: t("radar.stat_52w"), value: weekRangeLabel(row) },
    {
      label: t("radar.stat_next_earn"),
      value: earn?.next_date
        ? `${earn.next_date}${earn.next_estimated ? ` (${t("radar.earn_estimated")})` : ""}`
        : "—",
    },
  ];
});

onMounted(async () => {
  pulseLoading.value = true;
  pulseError.value = "";
  try {
    pulse.value = await api.researchPages.marketPulse();
  } catch (e) {
    pulseError.value = e.message || t("home.desk_market_error");
  } finally {
    pulseLoading.value = false;
  }
  try {
    screeners.value = await api.quoteScreeners();
  } catch {
    screeners.value = { gainers: [], losers: [], active: [], universe: [], sectors: [] };
  }
  const seedTickers = [
    ...pinnedTickers.value,
    ...publicTickers(trackedCompanies.value),
  ].slice(0, 8);
  alertRules.value = ensureDefaultAlertRules(seedTickers);
  if (hasScreenQuery(route.query)) {
    if (route.query.screen) applySavedScreen(String(route.query.screen));
    else {
      const filters = screenFiltersFromQuery(route.query);
      screenerSector.value = filters.sector;
      screenerCap.value = filters.cap;
      screenerMinChange.value = filters.minChange;
      screenerMinVolume.value = filters.minVolume;
      screenerQuery.value = filters.query;
      tab.value = "screener";
    }
  }
  const lastDesk = loadLastDeskId();
  if (lastDesk && !route.query.ticker && !route.query.desk && !hasScreenQuery(route.query)) {
    applyDesk(lastDesk);
  }
  window.addEventListener("keydown", onMarketKeydown);
  loadServerAlerts();
  loadLedger();
});

watch(
  () => [
    screenerSector.value,
    screenerCap.value,
    screenerMinChange.value,
    screenerMinVolume.value,
    screenerQuery.value,
    tab.value,
  ],
  () => {
    if (tab.value === "screener") syncScreenToRoute();
  },
);

watch(
  () => [selectedTicker.value, chartRange.value],
  async ([ticker]) => {
    if (!ticker) {
      chart.value = null;
      return;
    }
    chartLoading.value = true;
    chartError.value = "";
    try {
      chart.value = await api.quoteChart(ticker, chartRange.value);
      if (chart.value?.points?.length) {
        chartPointsCache.value = {
          ...chartPointsCache.value,
          [ticker]: chart.value.points,
        };
      }
    } catch (e) {
      chart.value = null;
      chartError.value = e.message || t("radar.chart_error");
    } finally {
      chartLoading.value = false;
    }
  },
  { immediate: true },
);

watch(
  () => [deskBTicker.value, chartRange.value, twoUp.value],
  async ([ticker]) => {
    if (!twoUp.value || !ticker || ticker === selectedTicker.value) {
      if (!twoUp.value) secondaryTicker.value = "";
      secondaryChart.value = null;
      secondaryWorkspace.value = null;
      return;
    }
    secondaryTicker.value = ticker;
    secondaryLoading.value = true;
    try {
      const [chartPayload, workspacePayload] = await Promise.all([
        api.quoteChart(ticker, chartRange.value),
        api.quoteWorkspace(ticker).catch(() => null),
      ]);
      secondaryChart.value = chartPayload;
      secondaryWorkspace.value = workspacePayload;
    } catch {
      secondaryChart.value = null;
      secondaryWorkspace.value = null;
    } finally {
      secondaryLoading.value = false;
    }
  },
  { immediate: true },
);

async function prefetchWeiSparks() {
  const missing = WEI_TICKERS.filter((ticker) => !(chartPointsCache.value[ticker] || []).length);
  if (!missing.length) return;
  const rows = await Promise.all(
    missing.map(async (ticker) => {
      try {
        const payload = await api.quoteChart(ticker, "3mo");
        return [ticker, payload?.points || []];
      } catch {
        return [ticker, []];
      }
    }),
  );
  const next = { ...chartPointsCache.value };
  for (const [ticker, points] of rows) {
    if (points.length) next[ticker] = points;
  }
  chartPointsCache.value = next;
}
prefetchWeiSparks();

watch(
  () => [hpCompare.value.join(","), chartRange.value],
  async () => {
    const tickers = hpCompare.value.filter((ticker) => ticker !== selectedTicker.value);
    if (!tickers.length) {
      hpSeries.value = [];
      return;
    }
    const rows = await Promise.all(
      tickers.map(async (ticker) => {
        try {
          const payload = await api.quoteChart(ticker, chartRange.value);
          return { ticker, points: payload?.points || [] };
        } catch {
          return { ticker, points: [] };
        }
      }),
    );
    hpSeries.value = rows.filter((row) => row.points.length);
  },
  { immediate: true },
);

watch(
  () => [selectedTicker.value, competitorTickers.value.join(",")],
  async ([ticker]) => {
    if (!ticker) {
      workspace.value = null;
      peers.value = null;
      return;
    }
    workspaceLoading.value = true;
    peersLoading.value = true;
    try {
      workspace.value = await api.quoteWorkspace(ticker);
    } catch {
      workspace.value = null;
    } finally {
      workspaceLoading.value = false;
    }
    try {
      peers.value = await api.quotePeers(ticker, competitorTickers.value);
      const next = { ...returnCache.value };
      for (const row of [peers.value?.primary, ...(peers.value?.peers || [])]) {
        if (!row?.ticker) continue;
        next[row.ticker] = {
          ytd: row.ret_ytd ?? next[row.ticker]?.ytd ?? null,
          vsSpy1y: row.vs_spy_1y ?? next[row.ticker]?.vsSpy1y ?? null,
        };
      }
      returnCache.value = next;
    } catch {
      peers.value = null;
    } finally {
      peersLoading.value = false;
    }
  },
  { immediate: true },
);


watch(
  () => route.query.panel,
  (value) => {
    focusPanel.value = String(value || "");
    if (focusPanel.value === "calendar") {
      tab.value = "watchlist";
    }
    if (focusPanel.value === "screener") {
      tab.value = "screener";
    }
    if (focusPanel.value === "fa") {
      workspaceTab.value = "financials";
    }
    if (focusPanel.value === "owners") {
      workspaceTab.value = "holders";
    }
    if (focusPanel.value === "heatmap") {
      tab.value = "screener";
    }
    if (route.query.range) {
      chartRange.value = String(route.query.range);
    }
    if (route.query.two) {
      twoUp.value = true;
    }
    if (route.query.ics) {
      window.setTimeout(() => exportCalendar(), 80);
    }
    if (route.query.week) calendarView.value = "week";
    if (route.query.screen) {
      applySavedScreen(String(route.query.screen));
    } else if (hasScreenQuery(route.query) && !route.query.screen) {
      const filters = screenFiltersFromQuery(route.query);
      screenerSector.value = filters.sector;
      screenerCap.value = filters.cap;
      screenerMinChange.value = filters.minChange;
      screenerMinVolume.value = filters.minVolume;
      screenerQuery.value = filters.query;
      tab.value = "screener";
    }
    if (route.query.desk) {
      applyDesk(String(route.query.desk));
    }
    window.setTimeout(() => {
      const id =
        focusPanel.value === "peers"
          ? "market-comp"
          : focusPanel.value === "calendar"
            ? "market-calendar"
            : focusPanel.value === "news"
              ? "market-news"
              : focusPanel.value === "hp" || focusPanel.value === "session"
                ? "market-hp"
                : focusPanel.value === "wei"
                  ? "market-wei"
                  : focusPanel.value === "alerts"
                    ? "market-alerts"
                    : focusPanel.value === "screener" || focusPanel.value === "heatmap"
                      ? "market-board"
                      : focusPanel.value === "rrg"
                        ? "market-rrg"
                        : focusPanel.value === "filings"
                          ? "market-filings"
                          : focusPanel.value === "desk"
                            ? "market-desks"
                            : focusPanel.value === "notes"
                              ? "market-notes"
                              : focusPanel.value === "pair"
                                ? "market-pair"
                                : focusPanel.value === "breadth"
                                  ? "market-breadth"
                                  : focusPanel.value === "risk"
                                    ? "market-risk"
                                    : focusPanel.value === "ladder"
                                      ? "market-ladder"
                                      : focusPanel.value === "fa" || focusPanel.value === "owners"
                                        ? "market-workspace"
                                        : "";
      if (id) document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  },
  { immediate: true },
);

watch(
  calendarTickers,
  async (tickers) => {
    calendarLoading.value = true;
    try {
      calendar.value = await api.quoteCalendar(tickers);
    } catch {
      calendar.value = { events: [] };
    } finally {
      calendarLoading.value = false;
    }
  },
  { immediate: true },
);

watch(
  () => route.query.ticker,
  (value) => {
    const ticker = String(value || "").trim().toUpperCase();
    if (ticker && ticker !== selectedTicker.value) selectTicker(ticker);
  },
);

watch(
  () => route.query.two,
  (value) => {
    twoUp.value = Boolean(value);
  },
);

watch(
  () => route.query.wide,
  (value) => {
    deskExpanded.value = value === "1" || value === "true";
  },
);

watch(query, (value) => {
  window.clearTimeout(searchTimer);
  const q = String(value || "").trim();
  if (!q) {
    remoteMatches.value = [];
    return;
  }
  showSuggestions.value = true;
  searchTimer = window.setTimeout(async () => {
    try {
      const payload = await api.quoteSearch(q);
      if (query.value.trim() !== q) return;
      remoteMatches.value = payload?.matches || [];
    } catch {
      if (query.value.trim() === q) remoteMatches.value = [];
    }
  }, 200);
});

onUnmounted(() => {
  window.clearTimeout(searchTimer);
  window.removeEventListener("keydown", onMarketKeydown);
});

function money(value, currency = "USD", compactMode = false) {
  if (!Number.isFinite(Number(value))) return "—";
  if (compactMode && Math.abs(Number(value)) >= 1000) {
    return formatCompactNumber(value, { currency: currency === "USD" });
  }
  return lastPriceLabel({ last: Number(value), currency }) || "—";
}

function compact(value) {
  if (!Number.isFinite(Number(value))) return "—";
  return formatCompactNumber(value);
}

function number(value) {
  if (!Number.isFinite(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function percent(value) {
  if (!Number.isFinite(Number(value))) return "—";
  const n = Number(value);
  const pct = Math.abs(n) <= 1 && n !== 0 ? n * 100 : n;
  return `${pct.toFixed(2)}%`;
}

function retLabel(value) {
  if (!Number.isFinite(Number(value))) return "—";
  const n = Number(value);
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function weekRangeLabel(row) {
  if (!Number.isFinite(Number(row?.weekLow)) || !Number.isFinite(Number(row?.weekHigh))) {
    return "—";
  }
  return `${money(row.weekLow, row.currency)} – ${money(row.weekHigh, row.currency)}`;
}

function priceLabel(row) {
  if (row?.last == null) return "—";
  return lastPriceLabel({ last: Number(row.last), currency: row.currency || "USD" }) || "—";
}

function selectTicker(ticker, companyId = null) {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!symbol) return;
  selectedTicker.value = symbol;
  tickerNote.value = loadTickerNote(symbol);
  recentTickers.value = pushRecentTicker(symbol);
  if (!extraTickers.value.includes(symbol)) {
    extraTickers.value = [...extraTickers.value, symbol].slice(-12);
  }
  if (String(route.query.ticker || "").toUpperCase() !== symbol) {
    router.replace({ query: { ...route.query, ticker: symbol } });
  }
  if (companyId && !companyList.value.some((row) => String(row.ticker || "").toUpperCase() === symbol)) {
    return;
  }
}

function selectRow(row) {
  if (row?.ticker) selectTicker(row.ticker, row.companyId);
}

function pickSuggestion(row) {
  showSuggestions.value = false;
  query.value = row.ticker || row.name || "";
  if (row.ticker) {
    selectTicker(row.ticker, row.companyId);
    return;
  }
  if (row.companyId) {
    router.push({ name: "research", params: { companyId: row.companyId } });
  }
}

function hideSuggestions() {
  window.setTimeout(() => {
    showSuggestions.value = false;
  }, 120);
}

function submitSearch() {
  const matches = suggestions.value;
  if (matches[0]) {
    pickSuggestion(matches[0]);
    return;
  }
  const ticker = query.value.trim().toUpperCase();
  if (ticker) selectTicker(ticker);
}

function openCompany(row) {
  const id = row?.companyId || selected.value?.companyId;
  if (id) router.push({ name: "research", params: { companyId: id } });
}

function togglePinSelected() {
  pinnedTickers.value = togglePinnedTicker(selectedTicker.value);
}

function addHpTicker() {
  const symbol = String(hpInput.value || "").trim().toUpperCase();
  if (!symbol) return;
  hpCompare.value = toggleHpCompare(symbol, hpCompare.value);
  if (!hpCompare.value.includes(symbol) && hpCompare.value.length >= 4) {
    hpInput.value = "";
    return;
  }
  hpInput.value = "";
}

function removeHpTicker(ticker) {
  hpCompare.value = saveHpCompare(hpCompare.value.filter((row) => row !== ticker));
}

function applySavedScreen(idOrName) {
  const screen = findSavedScreen(idOrName, savedScreens.value);
  if (!screen) return;
  screenerSector.value = screen.filters.sector || "";
  screenerCap.value = screen.filters.cap || "";
  screenerMinChange.value = screen.filters.minChange ?? "";
  screenerMinVolume.value = screen.filters.minVolume ?? "";
  screenerQuery.value = screen.filters.query || "";
  tab.value = "screener";
  router.replace({
    query: {
      ...route.query,
      panel: "screener",
      screen: screen.name,
      ...screenFiltersToQuery(screen.filters),
    },
  });
}

function persistCurrentScreen() {
  const name = String(screenNameDraft.value || "").trim();
  if (!name) return;
  savedScreens.value = saveScreen(name, {
    sector: screenerSector.value,
    cap: screenerCap.value,
    minChange: screenerMinChange.value,
    minVolume: screenerMinVolume.value,
    query: screenerQuery.value,
  });
  screenNameDraft.value = "";
}

function dropSavedScreen(id) {
  savedScreens.value = deleteSavedScreen(id);
}

function persistCurrentDesk() {
  const name = String(deskNameDraft.value || "").trim();
  if (!name) return;
  savedDesks.value = saveDesk(name, {
    ticker: selectedTicker.value,
    panel: focusPanel.value,
    workspaceTab: workspaceTab.value,
    chartRange: chartRange.value,
    hpCompare: hpCompare.value,
    newsScope: newsScope.value,
    calendarFilter: calendarFilter.value,
    tab: tab.value,
    twoUp: twoUp.value,
    secondaryTicker: secondaryTicker.value || deskBTicker.value || null,
    watchGroupFilter: watchGroupFilter.value,
    watchColumns: watchColumns.value,
    corrBench: corrBench.value,
    pairMode: pairMode.value,
    scrollY: typeof window !== "undefined" ? window.scrollY : null,
    screen: {
      sector: screenerSector.value,
      cap: screenerCap.value,
      minChange: screenerMinChange.value,
      minVolume: screenerMinVolume.value,
      query: screenerQuery.value,
    },
  });
  const desk = savedDesks.value[0];
  if (desk?.id) setLastDeskId(desk.id);
  deskNameDraft.value = "";
}

function applyDesk(idOrName) {
  const desk = findDesk(idOrName, savedDesks.value);
  if (!desk) return;
  setLastDeskId(desk.id);
  if (desk.ticker) selectTicker(desk.ticker);
  if (desk.chartRange) chartRange.value = desk.chartRange;
  if (desk.workspaceTab) workspaceTab.value = desk.workspaceTab;
  if (desk.newsScope) newsScope.value = desk.newsScope;
  if (desk.calendarFilter) calendarFilter.value = desk.calendarFilter;
  if (desk.hpCompare?.length) hpCompare.value = desk.hpCompare;
  if (desk.screen) {
    screenerSector.value = desk.screen.sector || "";
    screenerCap.value = desk.screen.cap || "";
    screenerMinChange.value = desk.screen.minChange ?? "";
    screenerMinVolume.value = desk.screen.minVolume ?? "";
    screenerQuery.value = desk.screen.query || "";
  }
  if (desk.tab) tab.value = desk.tab;
  if (desk.panel === "screener" || desk.panel === "heatmap") tab.value = "screener";
  if (desk.panel === "calendar") tab.value = "watchlist";
  if (desk.twoUp != null) twoUp.value = Boolean(desk.twoUp);
  if (desk.secondaryTicker) secondaryTicker.value = desk.secondaryTicker;
  if (desk.watchGroupFilter) watchGroupFilter.value = desk.watchGroupFilter;
  if (desk.watchColumns?.length) watchColumns.value = saveWatchColumns(desk.watchColumns);
  if (desk.corrBench) corrBench.value = desk.corrBench;
  if (desk.pairMode) pairMode.value = desk.pairMode;
  if (Number.isFinite(desk.scrollY)) {
    window.setTimeout(() => window.scrollTo({ top: desk.scrollY, behavior: "smooth" }), 80);
  }
}

function dropDesk(id) {
  savedDesks.value = deleteDesk(id);
}

function setSessionView() {
  chartRange.value = "1d";
}

function flipWatchColumn(id) {
  watchColumns.value = toggleWatchColumn(id, watchColumns.value);
}

function snoozeAlert(alert) {
  alertMutes.value = muteAlert(alert, { minutes: 60 });
  alertHistory.value = loadAlertHistory();
}

function silenceAlert(alert) {
  alertMutes.value = muteAlert(alert, { minutes: 60 * 24 });
  alertHistory.value = loadAlertHistory();
}

async function enableAlertNotify() {
  const permission = await requestAlertPermission();
  notifyEnabled.value = permission === "granted";
}

function cellValue(row, col) {
  if (col === "price") return priceLabel(row);
  if (col === "change") return row.change != null ? signedChange(row.change) : "—";
  if (col === "ytd") return retLabel(row.ytd);
  if (col === "vs_spy") {
    const vs1y = row.vsSpy1y;
    if (Number.isFinite(Number(vs1y))) return retLabel(vs1y);
    return retLabel(vsSpyDay(row.change, spyChange.value));
  }
  if (col === "volume") return compact(row.volume);
  if (col === "vol_ratio") {
    const ratio = volumeRatio(row.volume, row.avgVolume);
    return ratio != null ? `${ratio.toFixed(1)}×` : "—";
  }
  if (col === "next_earn") return earningsByTicker.value[row.ticker] || "—";
  if (col === "earn_days") {
    const stamp = earningsByTicker.value[row.ticker];
    const count = earningsCountdown(stamp);
    if (!count) return "—";
    return count.days < 0 ? "—" : `E${count.days}`;
  }
  if (col === "rsi" || col === "range_pos") {
    const enriched = enrichScreenerRow(row, {
      chartPoints: chartPointsCache.value[row.ticker] || [],
      earningsDate: earningsByTicker.value[row.ticker],
    });
    if (col === "rsi") return enriched.rsi != null ? enriched.rsi.toFixed(0) : "—";
    return enriched.rangePos != null ? `${enriched.rangePos.toFixed(0)}%` : "—";
  }
  return "—";
}

function colLabel(id) {
  return t(`radar.col_${id}`);
}

function alertLabel(alert) {
  if (alert.kind === "gap_up") {
    return t("radar.alert_gap_up", { ticker: alert.ticker, n: alert.change.toFixed(1) });
  }
  if (alert.kind === "gap_down") {
    return t("radar.alert_gap_down", {
      ticker: alert.ticker,
      n: Math.abs(alert.change).toFixed(1),
    });
  }
  if (alert.kind === "near_high") return t("radar.alert_near_high", { ticker: alert.ticker });
  if (alert.kind === "near_low") return t("radar.alert_near_low", { ticker: alert.ticker });
  if (alert.kind === "rule_pct_up") {
    return t("radar.alert_rule_pct_up", {
      ticker: alert.ticker,
      n: alert.change.toFixed(1),
      thr: alert.threshold,
    });
  }
  if (alert.kind === "rule_pct_down") {
    return t("radar.alert_rule_pct_down", {
      ticker: alert.ticker,
      n: Math.abs(alert.change).toFixed(1),
      thr: alert.threshold,
    });
  }
  if (alert.kind === "rule_volume") {
    return t("radar.alert_rule_volume", {
      ticker: alert.ticker,
      thr: alert.threshold,
    });
  }
  if (alert.kind === "rule_earnings") {
    return t("radar.alert_rule_earnings", {
      ticker: alert.ticker,
      n: alert.days,
    });
  }
  if (alert.kind === "rule_price_above") {
    return t("radar.alert_rule_price_above", {
      ticker: alert.ticker,
      n: Number(alert.threshold).toFixed(2),
    });
  }
  if (alert.kind === "rule_price_below") {
    return t("radar.alert_rule_price_below", {
      ticker: alert.ticker,
      n: Number(alert.threshold).toFixed(2),
    });
  }
  if (alert.kind === "rule_sma_above") {
    return t("radar.alert_rule_sma_above", {
      ticker: alert.ticker,
      n: alert.window || alert.threshold,
    });
  }
  if (alert.kind === "rule_sma_below") {
    return t("radar.alert_rule_sma_below", {
      ticker: alert.ticker,
      n: alert.window || alert.threshold,
    });
  }
  return alert.ticker;
}

function addPriceAlert() {
  const level = Number(priceAlertLevel.value);
  if (!selectedTicker.value || !Number.isFinite(level)) return;
  alertRules.value = upsertAlertRule({
    ticker: selectedTicker.value,
    kind: "price",
    threshold: level,
    direction: priceAlertDir.value,
    id: `${selectedTicker.value}-price-${level}`,
  });
  priceAlertLevel.value = "";
}

function addSmaAlert() {
  const window = Number(smaAlertWindow.value) || 50;
  if (!selectedTicker.value) return;
  alertRules.value = upsertAlertRule({
    ticker: selectedTicker.value,
    kind: "sma_cross",
    threshold: window,
    window,
    direction: "above",
    id: `${selectedTicker.value}-sma-${window}`,
  });
}

function persistNote() {
  saveTickerNote(selectedTicker.value, tickerNote.value);
}

function assignSelectedGroup(group) {
  pinGroups.value = setPinGroup(selectedTicker.value, group);
  if (!isPinnedTicker(selectedTicker.value, pinnedTickers.value)) {
    pinnedTickers.value = togglePinnedTicker(selectedTicker.value);
  }

function assignRowGroup(ticker, group) {
  pinGroups.value = setPinGroup(ticker, group);
  groupMenuTicker.value = "";
}

function openGroupMenu(row) {
  if (tab.value !== "watchlist") return;
  groupMenuTicker.value = row?.ticker || "";
}
}

function exportCalendar() {
  downloadIcs(upcomingEvents.value, "bsh-evts.ics");
}

function openHeatCell(cell) {
  screenerSector.value = cell.sector;
  tab.value = "screener";
  if (cell.leader?.ticker) selectTicker(cell.leader.ticker);
}

function toggleTwoUp() {
  twoUp.value = !twoUp.value;
  const query = { ...route.query };
  if (twoUp.value) query.two = "1";
  else delete query.two;
  router.replace({ query });
}

function toggleDeskExpanded() {
  deskExpanded.value = !deskExpanded.value;
  saveDeskLayout({ expanded: deskExpanded.value });
  const query = { ...route.query };
  if (deskExpanded.value) query.wide = "1";
  else delete query.wide;
  router.replace({ query });
}

function setSecondary(ticker) {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!symbol || symbol === selectedTicker.value) return;
  secondaryTicker.value = symbol;
  if (!hpCompare.value.includes(symbol)) {
    hpCompare.value = toggleHpCompare(symbol, hpCompare.value);
  }
  twoUp.value = true;
  const query = { ...route.query, two: "1" };
  router.replace({ query });
}

function normalizeCorrBench() {
  corrBench.value = String(corrBench.value || "SPY").trim().toUpperCase() || "SPY";
}

function groupCount(group) {
  const row = watchGroups.value.find((item) => item.group === group);
  return row?.tickers?.length || 0;
}

watch(
  alerts,
  (rows) => {
    if (!rows.length) return;
    const fresh = freshAlerts(rows);
    if (fresh.length) {
      alertHistory.value = loadAlertHistory();
      // Mirror browser fires into the server history so "while away"
      // digests on other devices include them. Dedupe key matches the
      // local notified-key shape (ticker+kind+day).
      const day = new Date().toISOString().slice(0, 10);
      api
        .recordAlertEvents(
          fresh.map((row) => ({
            ticker: row.ticker,
            kind: row.kind,
            message: alertLabel(row),
            dedupe_key: `browser:${row.ticker}:${row.kind}:${day}`,
            source: "browser",
          })),
        )
        .catch(() => {});
    }
    if (!notifyEnabled.value || !fresh.length) return;
    notifyAlerts(fresh, { title: t("radar.alerts_label") });
  },
);

function alertsSeenStamp() {
  try {
    return window.localStorage.getItem(ALERTS_SEEN_KEY) || null;
  } catch {
    return null;
  }
}

async function loadServerAlerts() {
  try {
    const payload = await api.alertEvents(alertsSeenStamp(), 30);
    serverAlerts.value = payload?.events || [];
  } catch {
    serverAlerts.value = [];
  }
}

function markAlertsSeen() {
  try {
    window.localStorage.setItem(ALERTS_SEEN_KEY, new Date().toISOString());
  } catch {
    // ignore
  }
  serverAlerts.value = [];
}

async function loadLedger() {
  try {
    const payload = await api.signalLedger();
    ledgerEntries.value = payload?.entries || [];
  } catch {
    ledgerEntries.value = [];
  }
}

async function logSignal(direction) {
  const row = selected.value;
  if (!row?.ticker) return;
  try {
    await api.recordSignal({
      ticker: row.ticker,
      direction,
      label: tickerNote.value || `${row.ticker} desk call`,
      source: "market-desk",
      price_at_signal: Number.isFinite(Number(row.last)) ? Number(row.last) : null,
    });
    await loadLedger();
    signalToast.value = t("radar.signal_logged", { ticker: row.ticker });
  } catch (e) {
    signalToast.value = e?.message || t("radar.signal_log_failed");
  }
  window.clearTimeout(signalToastTimer);
  signalToastTimer = window.setTimeout(() => {
    signalToast.value = "";
  }, 2500);
}

function reactionFor(item) {
  const ids = (item?.companyIds || []).map(String);
  let ticker = "";
  for (const id of ids) {
    const company = companyList.value.find((row) => String(row.id) === id);
    const symbol = String(company?.ticker || "").trim().toUpperCase();
    if (symbol) {
      ticker = symbol;
      break;
    }
  }
  if (!ticker) return null;
  const pct = headlineReaction(
    item.captured_at || item.ts,
    chartPointsCache.value[ticker] || [],
  );
  if (pct == null || Math.abs(pct) < 0.05) return null;
  return { ticker, pct };
}

watch(
  () => breadth.value.advancePct,
  (value) => {
    if (!Number.isFinite(Number(value))) return;
    breadthHistory.value = [...breadthHistory.value, Number(value)].slice(-24);
  },
);

function openAsk() {
  if (!openCopilot) return;
  const row = selected.value;
  if (!row?.ticker) return;
  openCopilot({
    companyId: row.companyId || null,
    context: {
      surface: "market_desk",
      tab: "quote",
      selection: {
        ticker: row.ticker,
        name: row.name,
        change: row.change,
        company_id: row.companyId,
      },
    },
  });
}

function askWhyMoving() {
  if (!openCopilot) return;
  const row = selected.value;
  if (!row?.ticker) return;
  const headlines = selectedHeadlines.value
    .slice(0, 4)
    .map((item) => `- ${item.title}`)
    .join("\n");
  const filings = selectedFilings.value
    .slice(0, 4)
    .map((item) => `- ${item.form ? `[${item.form}] ` : ""}${item.title}`)
    .join("\n");
  const hits = researchHits.value
    .slice(0, 4)
    .map((item) => `- (${item.kind}) ${item.title}`)
    .join("\n");
  const ladderLine = ladder.value
    .filter((row) => row.value != null)
    .slice(0, 5)
    .map((row) => `${row.id} ${Number(row.value).toFixed(1)}%`)
    .join(" · ");
  const gap = gapStats.value;
  const note = tickerNote.value ? `Note: ${tickerNote.value}` : "";
  const packet = [
    t("radar.copilot_prompt", {
      ticker: row.ticker,
      change: row.change != null ? signedChange(row.change) : "—",
      headlines: headlines || t("radar.copilot_no_headlines"),
    }),
    gap.gap != null
      ? `Gap ${gap.gap.toFixed(2)}% · session ${gap.session != null ? gap.session.toFixed(2) : "—"}%`
      : "",
    ladderLine ? `Returns: ${ladderLine}` : "",
    note,
    filings ? `Filings:\n${filings}` : "",
    hits ? `Research:\n${hits}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
  openCopilot({
    companyId: row.companyId || null,
    prompt: packet,
    context: {
      surface: "market_desk",
      tab: "quote",
      selection: {
        ticker: row.ticker,
        name: row.name,
        change: row.change,
        company_id: row.companyId,
        note: tickerNote.value || "",
        gap: gapStats.value,
        ladder: ladder.value,
        headlines: selectedHeadlines.value.slice(0, 6).map((item) => ({
          title: item.title,
          id: item.id,
        })),
        filings: selectedFilings.value.slice(0, 6).map((item) => ({
          title: item.title,
          form: item.form,
        })),
        research: researchHits.value.slice(0, 6),
      },
    },
  });
}

function onMarketKeydown(event) {
  const target = event.target;
  const tag = String(target?.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select" || target?.isContentEditable) return;
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const key = event.key;
  const rangeMap = {
    "1": "1d",
    "2": "5d",
    "3": "1mo",
    "4": "6mo",
    "5": "ytd",
    "6": "1y",
    "7": "5y",
    "8": "max",
  };
  if (rangeMap[key]) {
    event.preventDefault();
    chartRange.value = rangeMap[key];
    return;
  }
  if (key === "?" || (event.shiftKey && key === "/")) {
    event.preventDefault();
    showKeyHelp.value = !showKeyHelp.value;
    return;
  }
  if (key === "Escape" && showKeyHelp.value) {
    event.preventDefault();
    showKeyHelp.value = false;
    return;
  }
  if (key === "p" || key === "P") {
    event.preventDefault();
    togglePinSelected();
    return;
  }
  if (key === "m" || key === "M") {
    event.preventDefault();
    if (alerts.value[0]) snoozeAlert(alerts.value[0]);
    return;
  }
  if (key === "t" || key === "T") {
    event.preventDefault();
    toggleTwoUp();
    return;
  }
  if (key === "n" || key === "N") {
    event.preventDefault();
    document.getElementById("market-notes")?.scrollIntoView({ behavior: "smooth", block: "center" });
    document.querySelector("#market-notes textarea")?.focus();
    return;
  }
  if (key === "[") {
    event.preventDefault();
    const idx = workspaceTabs.indexOf(workspaceTab.value);
    workspaceTab.value = workspaceTabs[(idx - 1 + workspaceTabs.length) % workspaceTabs.length];
    return;
  }
  if (key === "]") {
    event.preventDefault();
    const idx = workspaceTabs.indexOf(workspaceTab.value);
    workspaceTab.value = workspaceTabs[(idx + 1) % workspaceTabs.length];
    return;
  }
  const jumps = { g: "market-comp", G: "market-comp", c: "market-calendar", C: "market-calendar", h: "market-board", H: "market-board", w: "market-wei", W: "market-wei" };
  if (jumps[key]) {
    event.preventDefault();
    document.getElementById(jumps[key])?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function formatAlertTime(at) {
  const stamp = Number(at);
  if (!Number.isFinite(stamp)) return "";
  return new Date(stamp).toLocaleString();
}

function shareScreenUrl() {
  const query = {
    ...route.query,
    panel: "screener",
    ...screenFiltersToQuery({
      sector: screenerSector.value,
      cap: screenerCap.value,
      minChange: screenerMinChange.value,
      minVolume: screenerMinVolume.value,
      query: screenerQuery.value,
    }),
  };
  router.replace({ query });
  const url = `${window.location.origin}${window.location.pathname}?${new URLSearchParams(query).toString()}`;
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(url);
  shareToast.value = t("radar.eqs_copied");
  window.setTimeout(() => {
    shareToast.value = "";
  }, 1800);
}

function syncScreenToRoute() {
  if (tab.value !== "screener") return;
  const next = {
    ...route.query,
    panel: "screener",
    ...screenFiltersToQuery({
      sector: screenerSector.value,
      cap: screenerCap.value,
      minChange: screenerMinChange.value,
      minVolume: screenerMinVolume.value,
      query: screenerQuery.value,
    }),
  };
  router.replace({ query: next });
}

function eventTitle(event) {
  if (event?.kind === "dividend") return t("radar.event_dividend");
  if (event?.kind === "macro") return event.title || t("radar.event_macro");
  if (event?.kind === "catalyst") return event.title || t("radar.event_catalyst");
  return event?.title || t("radar.event_earnings");
}

function asOfLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
</script>

<template>
  <div class="yf-page">
    <header class="mb-5 flex flex-col gap-3">
      <form class="yf-search w-full max-w-xl" @submit.prevent="submitSearch">
        <Search class="yf-search-icon" />
        <input
          v-model="query"
          type="search"
          class="yf-search-input focus-ring"
          :placeholder="t('radar.search_placeholder')"
          :aria-label="t('radar.search_placeholder')"
          autocomplete="off"
          @focus="showSuggestions = suggestions.length > 0"
          @blur="hideSuggestions"
        />
        <div v-if="showSuggestions && suggestions.length" class="yf-search-menu" role="listbox">
          <button
            v-for="row in suggestions"
            :key="`${row.kind}-${row.ticker || row.companyId}`"
            type="button"
            class="yf-search-item"
            @mousedown.prevent="pickSuggestion(row)"
          >
            <span class="font-display text-headline tabular">{{ row.ticker || "—" }}</span>
            <span class="truncate text-footnote text-ink-muted">{{ row.name }}</span>
          </button>
        </div>
      </form>
      <div class="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 class="font-display text-large-title text-ink-primary">
            {{ t("radar.page_title") }}
          </h1>
          <p class="mt-1 text-callout text-ink-secondary">
            {{ t("radar.page_subtitle") }}
          </p>
        </div>
        <button type="button" class="yf-kb-hint self-start focus-ring" @click="showKeyHelp = true">
          {{ t("radar.kb_hint_short") }}
        </button>
      </div>
      <section id="market-desks" class="flex flex-wrap items-center gap-2" :data-focus="focusPanel === 'desk'">
        <span class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
          {{ t("radar.desks_label") }}
        </span>
        <button
          v-for="desk in savedDesks"
          :key="desk.id"
          type="button"
          class="yf-range-item focus-ring"
          @click="applyDesk(desk.id)"
          @dblclick="dropDesk(desk.id)"
          :title="t('radar.eqs_delete_hint')"
        >
          {{ desk.name }}
        </button>
        <button type="button" class="yf-range-item focus-ring" :data-selected="showDeskSave" @click="showDeskSave = !showDeskSave">
          {{ t("radar.desk_save") }}
        </button>
        <form v-if="showDeskSave" class="flex items-center gap-1" @submit.prevent="persistCurrentDesk">
          <input
            v-model="deskNameDraft"
            type="text"
            class="yf-screener-field focus-ring !mb-0 max-w-[9rem] px-2 py-1 text-caption1"
            :placeholder="t('radar.desk_save_ph')"
            :aria-label="t('radar.desk_save_ph')"
          />
          <button type="submit" class="yf-range-item focus-ring">{{ t("radar.desk_save_btn") }}</button>
        </form>
        <template v-if="recentTickers.length">
          <span class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
            {{ t("radar.recents_label") }}
          </span>
          <button
            v-for="ticker in recentTickers"
            :key="`recent-${ticker}`"
            type="button"
            class="yf-range-item focus-ring"
            @click="selectTicker(ticker)"
          >
            {{ ticker }}
          </button>
        </template>
      </section>
    </header>

    <div
      v-if="showKeyHelp"
      class="yf-kb-help"
      role="dialog"
      :aria-label="t('radar.kb_help_title')"
      @click.self="showKeyHelp = false"
    >
      <div class="yf-kb-help-card">
        <div class="mb-2 flex items-center justify-between gap-2">
          <h2 class="font-display text-headline">{{ t("radar.kb_help_title") }}</h2>
          <button type="button" class="yf-range-item focus-ring" @click="showKeyHelp = false">{{ t("cmd.esc") }}</button>
        </div>
        <p class="text-callout text-ink-secondary">{{ t("radar.kb_hint") }}</p>
      </div>
    </div>

    <section
      id="market-alerts"
      class="mb-4 news-grouped px-4 py-3"
      :aria-label="t('radar.alerts_label')"
      :data-focus="focusPanel === 'alerts'"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
          {{ t("radar.alerts_label") }}
        </div>
        <div class="flex flex-wrap gap-1">
          <button
            type="button"
            class="yf-range-item focus-ring"
            :data-selected="showAlertRules"
            @click="showAlertRules = !showAlertRules"
          >
            {{ t("radar.alert_rules") }}
          </button>
          <button
            v-if="alertHistory.length"
            type="button"
            class="yf-range-item focus-ring"
            :data-selected="showAlertHistory"
            @click="showAlertHistory = !showAlertHistory"
          >
            {{ t("radar.alert_history") }}
          </button>
          <button
            v-if="!notifyEnabled"
            type="button"
            class="yf-range-item focus-ring"
            @click="enableAlertNotify"
          >
            {{ t("radar.alert_notify") }}
          </button>
        </div>
      </div>
      <div v-if="alerts.length" class="mt-2 flex flex-wrap items-center gap-2">
        <span
          v-for="alert in alerts"
          :key="`${alert.ticker}-${alert.kind}-${alert.ruleId || ''}`"
          class="inline-flex items-center gap-1"
        >
          <button type="button" class="yf-range-item focus-ring" @click="selectTicker(alert.ticker)">
            {{ alertLabel(alert) }}
          </button>
          <button
            type="button"
            class="text-caption1 text-ink-muted focus-ring rounded-sm px-1"
            @click="snoozeAlert(alert)"
          >
            {{ t("radar.alert_snooze") }}
          </button>
          <button
            type="button"
            class="text-caption1 text-ink-muted focus-ring rounded-sm px-1"
            @click="silenceAlert(alert)"
          >
            {{ t("radar.alert_mute") }}
          </button>
        </span>
      </div>
      <p v-else class="mt-2 text-caption1 text-ink-muted">{{ t("radar.alerts_empty") }}</p>
      <div
        v-if="serverAlerts.length"
        class="mt-3 border-t border-[rgb(var(--color-border-subtle))] pt-2"
        data-testid="alerts-while-away"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
            {{ t("radar.alerts_while_away", { n: serverAlerts.length }) }}
          </span>
          <button type="button" class="yf-range-item focus-ring" @click="markAlertsSeen">
            {{ t("radar.alerts_mark_seen") }}
          </button>
        </div>
        <ul class="mt-1 space-y-0.5 text-caption1 text-ink-secondary">
          <li v-for="row in serverAlerts.slice(0, 8)" :key="row.id">
            <button
              type="button"
              class="focus-ring rounded-sm text-left"
              @click="selectTicker(row.ticker)"
            >
              {{ row.message || `${row.ticker} ${row.kind}` }}
            </button>
            <span class="ml-1 text-ink-subtle">{{ asOfLabel(row.fired_at) }}</span>
          </li>
        </ul>
      </div>
      <form
        v-if="showAlertRules"
        class="mt-3 flex flex-wrap items-center gap-1"
        @submit.prevent="addPriceAlert"
      >
        <input
          v-model="priceAlertLevel"
          type="number"
          step="0.01"
          class="yf-screener-field focus-ring !mb-0 max-w-[6rem] px-2 py-1 text-caption1"
          :placeholder="t('radar.alert_price_ph')"
        />
        <select v-model="priceAlertDir" class="yf-range-item focus-ring">
          <option value="above">≥</option>
          <option value="below">≤</option>
        </select>
        <button type="submit" class="yf-range-item focus-ring">{{ t("radar.alert_price_add") }}</button>
        <button type="button" class="yf-range-item focus-ring" @click="addSmaAlert">
          {{ t("radar.alert_sma_add", { n: smaAlertWindow }) }}
        </button>
      </form>
      <div v-if="showAlertHistory && alertHistory.length" class="mt-3">
        <div class="mb-1 flex items-center justify-between gap-2">
          <span class="text-caption1 text-ink-muted">{{ t("radar.alert_history") }}</span>
          <button type="button" class="yf-range-item focus-ring" @click="alertHistory = clearAlertHistory()">
            {{ t("radar.alert_history_clear") }}
          </button>
        </div>
        <ul class="yf-alert-hist">
          <li v-for="row in alertHistory.slice(0, 12)" :key="row.id">
            <button type="button" class="focus-ring" @click="selectTicker(row.ticker)">
              {{ row.ticker }}
            </button>
            · {{ row.action }} · {{ row.kind }}
            <span class="text-ink-muted">{{ formatAlertTime(row.at) }}</span>
          </li>
        </ul>
      </div>
    </section>

    <section id="market-wei" class="mb-5" :aria-label="t('radar.wei_label')" :data-focus="focusPanel === 'wei'">
      <div class="mb-2 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
            {{ t("radar.wei_label") }}
          </div>
          <p class="mt-0.5 text-footnote text-ink-secondary">
            {{ postureLabel }}
            <span v-if="topSignal"> · {{ topSignal }}</span>
          </p>
        </div>
      </div>
      <div class="yf-index-scroller">
        <button
          v-for="card in indexes"
          :key="card.ticker"
          type="button"
          class="yf-index-card focus-ring"
          :data-selected="selected?.ticker === card.ticker"
          @click="selectRow(card)"
        >
          <div class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
            {{ card.label }}
          </div>
          <div class="mt-1 font-display text-headline tabular text-ink-primary">
            {{ card.ticker }}
          </div>
          <div class="mt-2 flex items-baseline justify-between gap-2">
            <span class="mono-data text-title3 tabular text-ink-primary">
              {{ priceLabel(card) }}
            </span>
            <span
              v-if="card.change != null"
              class="mono-data text-footnote font-semibold tabular"
              :class="card.change >= 0 ? 'text-success' : 'text-danger'"
            >
              {{ signedChange(card.change) }}
            </span>
            <span v-else class="text-caption1 text-ink-subtle">
              {{ t("tracking.quote_pending") }}
            </span>
          </div>
          <QuoteSparkline
            v-if="card.spark?.length"
            class="mt-2"
            :values="card.spark"
            :label="card.ticker"
          />
        </button>
      </div>
    </section>

    <div
      class="items-start gap-6"
      :class="deskExpanded ? 'space-y-6' : 'grid lg:grid-cols-12'"
    >
      <div class="min-w-0 space-y-5" :class="deskExpanded ? '' : 'lg:col-span-8'">
        <article v-if="selected" class="news-grouped p-5">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
                {{ selected.exchange || t("radar.selected_quote") }}
              </div>
              <h2 class="mt-1 font-display text-title2 text-ink-primary">
                {{ selected.ticker }}
                <span class="ml-2 text-callout font-normal text-ink-muted">
                  {{ selected.label || selected.name }}
                </span>
              </h2>
              <p v-if="asOfLabel(selected.asOf)" class="mt-1 text-caption1 text-ink-muted">
                {{ t("radar.as_of", { when: asOfLabel(selected.asOf) }) }}
                <span
                  v-if="selectedStaleness?.stale"
                  class="ml-1 rounded-pill bg-notice/15 px-1.5 py-0.5 text-caption2 font-semibold uppercase tracking-[0.04em] text-notice"
                >
                  {{ t("radar.stale_quote", { n: selectedStaleness.ageMinutes }) }}
                </span>
              </p>
              <div v-if="selected.companyId || openCopilot" class="mt-1.5 flex flex-wrap items-center gap-2">
                <button
                  v-if="openCopilot"
                  type="button"
                  class="btn-filled btn-sm focus-ring inline-flex items-center gap-1.5"
                  @click="openAsk"
                >
                  {{ t("copilot.ask_short") }}
                </button>
                <RouterLink
                  v-if="selected.companyId"
                  class="text-caption1 font-medium text-accent-ink focus-ring rounded-pill px-1"
                  :to="{ name: 'research', params: { companyId: selected.companyId } }"
                >
                  {{ t("radar.open_company") }}
                </RouterLink>
                <RouterLink
                  v-if="selected.companyId"
                  class="text-caption1 font-medium text-accent-ink focus-ring rounded-pill px-1"
                  :to="{ name: 'research', params: { companyId: selected.companyId }, query: { tab: 'console' } }"
                >
                  {{ t("radar.open_console") }}
                </RouterLink>
              </div>
            </div>
            <div class="text-right">
              <div class="mb-2 flex items-start justify-end gap-2">
                <button
                  type="button"
                  class="yf-range-item focus-ring"
                  :data-selected="twoUp"
                  @click="toggleTwoUp"
                >
                  {{ t("radar.two_up") }}
                </button>
                <CompanyFollowButton
                  v-if="selected.companyId"
                  :company-id="selected.companyId"
                  size="md"
                />
                <div class="flex flex-col items-end gap-1">
                  <button
                    type="button"
                    class="yf-range-item inline-flex items-center gap-1 focus-ring"
                    :data-selected="deskExpanded"
                    :aria-pressed="deskExpanded"
                    :aria-label="deskExpanded ? t('radar.collapse_desk') : t('radar.expand_desk')"
                    :title="deskExpanded ? t('radar.collapse_desk') : t('radar.expand_desk')"
                    @click="toggleDeskExpanded"
                  >
                    <Minimize2 v-if="deskExpanded" class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    <Maximize2 v-else class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    <span>{{ deskExpanded ? t("radar.collapse_desk") : t("radar.expand_desk") }}</span>
                  </button>
                  <button
                    type="button"
                    class="icon-btn !h-7 !w-7 focus-ring"
                    :aria-label="selectedPinned ? t('radar.unpin') : t('radar.pin')"
                    :title="selectedPinned ? t('radar.unpin') : t('radar.pin')"
                    :aria-pressed="selectedPinned"
                    @click="togglePinSelected"
                  >
                    <Star
                      class="h-4 w-4"
                      :class="selectedPinned ? 'text-notice' : ''"
                      :fill="selectedPinned ? 'currentColor' : 'none'"
                    />
                  </button>
                </div>
              </div>
              <div class="mono-data text-large-title tabular text-ink-primary">
                {{ priceLabel(selected) }}
              </div>
              <div
                v-if="selected.change != null"
                class="mt-1 inline-flex items-center gap-1 text-headline font-semibold tabular"
                :class="selected.change >= 0 ? 'text-success' : 'text-danger'"
              >
                <TrendingUp v-if="selected.change >= 0" class="h-4 w-4" />
                <TrendingDown v-else class="h-4 w-4" />
                <span v-if="selected.changeAbs != null">
                  {{ selected.changeAbs > 0 ? "+" : "" }}{{ Number(selected.changeAbs).toFixed(2) }}
                </span>
                {{ signedChange(selected.change) }}
              </div>
            </div>
          </div>

          <div class="yf-range mt-4" role="tablist" :aria-label="t('radar.chart_ranges')">
            <button
              v-for="span in CHART_RANGES"
              :key="span"
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="chartRange === span"
              @click="chartRange = span"
            >
              {{ rangeLabels[span] }}
            </button>
            <button
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="chartRange === '1d'"
              @click="setSessionView"
            >
              {{ t("radar.session_preset") }}
            </button>
          </div>
          <section
            id="market-hp"
            class="mt-3 flex flex-wrap items-center gap-2"
            :aria-label="t('radar.hp_label')"
            :data-focus="focusPanel === 'hp'"
          >
            <span class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.hp_label") }}
            </span>
            <button
              v-for="ticker in hpCompare"
              :key="`hp-${ticker}`"
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="true"
              @click="removeHpTicker(ticker)"
              :title="t('radar.hp_remove')"
            >
              {{ ticker }} ×
            </button>
            <form class="flex items-center gap-1" @submit.prevent="addHpTicker">
              <input
                v-model="hpInput"
                type="text"
                class="yf-screener-field focus-ring !mb-0 max-w-[7rem] px-2 py-1 text-caption1"
                :placeholder="t('radar.hp_add_ph')"
                :aria-label="t('radar.hp_add_ph')"
              />
              <button type="submit" class="yf-range-item focus-ring">{{ t("radar.hp_add") }}</button>
            </form>
          </section>
          <p v-if="chartError" class="mt-3 text-callout text-danger">{{ chartError }}</p>
          <div class="mt-3" :class="twoUp && deskBTicker ? 'grid gap-3 md:grid-cols-2' : ''">
            <div>
              <QuoteChart
                :points="chart?.points || []"
                :previous-close="selected.previousClose"
                :range="chartRange"
                :currency="selected.currency"
                :ticker="selected.ticker"
                :loading="chartLoading"
                :events="chartEvents"
                :peer-series="peerSeries"
                :tall="deskExpanded"
              />
            </div>
            <div v-if="twoUp && deskBTicker">
              <div class="mb-2 flex items-center justify-between gap-2">
                <h3 class="font-display text-headline tabular">{{ deskBTicker }}</h3>
                <button type="button" class="yf-range-item focus-ring" @click="selectTicker(deskBTicker)">
                  {{ t("radar.two_up_focus") }}
                </button>
              </div>
              <QuoteChart
                :points="secondaryChart?.points || []"
                :previous-close="secondaryChart?.previous_close ?? null"
                :range="chartRange"
                :currency="secondaryChart?.currency || selected.currency"
                :ticker="deskBTicker"
                :loading="secondaryLoading"
                :events="secondaryChartEvents"
                :peer-series="[]"
                :tall="deskExpanded"
              />
              <div v-if="secondaryLadder.length" class="yf-ladder mt-2">
                <div v-for="row in secondaryLadder" :key="`b-${row.id}`" class="yf-ladder-cell">
                  <div class="text-caption1 text-ink-muted">{{ t(row.labelKey) }}</div>
                  <div
                    class="mono-data tabular"
                    :class="Number(row.value) >= 0 ? 'text-success' : 'text-danger'"
                  >
                    {{ row.value != null ? signedChange(row.value) : "—" }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <section
            id="market-ladder"
            class="mt-4"
            :aria-label="t('radar.session_returns')"
            :data-focus="focusPanel === 'ladder'"
          >
            <h3 class="mb-2 text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.session_returns") }}
            </h3>
            <div
              v-if="gapStats.gap != null || gapStats.session != null"
              class="yf-gap mb-2"
              :aria-label="t('radar.gap_label')"
            >
              <span>
                {{ t("radar.gap_overnight") }}
                <strong :class="Number(gapStats.gap) >= 0 ? 'text-success' : 'text-danger'">
                  {{ gapStats.gap != null ? signedChange(gapStats.gap) : "—" }}
                </strong>
              </span>
              <span>
                {{ t("radar.gap_session") }}
                <strong :class="Number(gapStats.session) >= 0 ? 'text-success' : 'text-danger'">
                  {{ gapStats.session != null ? signedChange(gapStats.session) : "—" }}
                </strong>
              </span>
            </div>
            <div class="yf-ladder">
              <div v-for="row in visibleLadder" :key="row.id" class="yf-ladder-cell">
                <div class="text-caption1 text-ink-muted">{{ t(row.labelKey) }}</div>
                <div
                  class="mono-data tabular"
                  :class="Number(row.value) >= 0 ? 'text-success' : 'text-danger'"
                >
                  {{ row.value != null ? signedChange(row.value) : "—" }}
                </div>
              </div>
            </div>
          </section>

          <div class="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="showPair"
              :disabled="!hasPairPeer"
              @click="showPair = !showPair"
            >
              {{ t("radar.pair_toggle") }}
            </button>
            <span v-if="canShowPair && pairStats.last != null" class="text-caption1 text-ink-muted">
              {{ t("radar.pair_last") }}
              <span class="mono-data tabular text-ink-primary">{{ number(pairStats.last) }}</span>
              <template v-if="pairStats.z != null">
                · {{ t("radar.pair_z") }}
                <span class="mono-data tabular text-ink-primary">{{ number(pairStats.z) }}</span>
              </template>
            </span>
          </div>
          <section
            v-if="canShowPair"
            id="market-pair"
            class="mt-2"
            :aria-label="t('radar.pair_label')"
            :data-focus="focusPanel === 'pair'"
          >
            <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
                {{ t("radar.pair_label") }} · {{ selected.ticker }}/{{ pairPeerLabel }}
              </h3>
              <div class="flex gap-1">
                <button type="button" class="yf-range-item focus-ring" :data-selected="pairMode === 'diff'" @click="pairMode = 'diff'">
                  {{ t("radar.pair_diff") }}
                </button>
                <button type="button" class="yf-range-item focus-ring" :data-selected="pairMode === 'ratio'" @click="pairMode = 'ratio'">
                  {{ t("radar.pair_ratio") }}
                </button>
              </div>
            </div>
            <QuoteChart
              :points="pairPoints"
              :previous-close="null"
              :range="chartRange"
              currency=""
              :ticker="`${selected.ticker}-${pairPeerLabel}`"
              :loading="false"
              :events="[]"
              :peer-series="[]"
            />
          </section>

          <label id="market-notes" class="mt-3 block">
            <span class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.note_label") }}
            </span>
            <textarea
              v-model="tickerNote"
              class="mt-1 w-full rounded-md px-3 py-2 text-callout text-ink-primary focus-ring"
              rows="2"
              :placeholder="t('radar.note_ph')"
              @change="persistNote"
              @blur="persistNote"
            ></textarea>
          </label>
          <div class="mt-2 flex flex-wrap items-center gap-1" data-testid="signal-log">
            <span class="text-caption1 text-ink-muted">{{ t("radar.signal_log_label") }}</span>
            <button type="button" class="yf-range-item focus-ring" @click="logSignal('bullish')">
              {{ t("radar.signal_bullish") }}
            </button>
            <button type="button" class="yf-range-item focus-ring" @click="logSignal('bearish')">
              {{ t("radar.signal_bearish") }}
            </button>
            <span v-if="signalToast" class="text-caption1 text-accent-ink">{{ signalToast }}</span>
          </div>

          <section
            id="market-research"
            class="mt-4 news-grouped px-4 py-3"
            :aria-label="t('radar.research_rail')"
          >
            <div class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.research_rail") }}
            </div>
            <ul v-if="researchHits.length" class="yf-research-rail mt-2">
              <li v-for="hit in researchHits" :key="hit.id">
                <a
                  v-if="hit.url"
                  :href="hit.url"
                  target="_blank"
                  rel="noopener"
                  class="text-callout text-ink-primary focus-ring"
                >{{ hit.title }}</a>
                <button
                  v-else-if="hit.companyId"
                  type="button"
                  class="text-callout focus-ring"
                  @click="router.push({ name: 'research', params: { companyId: hit.companyId } })"
                >
                  {{ hit.title }}
                </button>
                <span v-else class="text-callout">{{ hit.title }}</span>
                <span class="ml-1 text-caption1 text-ink-muted">{{ hit.kind }}</span>
              </li>
            </ul>
            <p v-else class="mt-1 text-caption1 text-ink-muted">{{ t("radar.research_empty") }}</p>
          </section>

          <section
            id="market-comp"
            class="mt-5"
            :aria-label="t('radar.comp_label')"
            :data-focus="focusPanel === 'peers'"
          >
            <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
                {{ t("radar.comp_label") }}
              </h3>
              <label class="inline-flex items-center gap-1 text-caption1 text-ink-muted">
                {{ t("radar.corr_bench") }}
                <input
                  v-model="corrBench"
                  type="text"
                  maxlength="8"
                  class="yf-screener-field focus-ring !mb-0 max-w-[4.5rem] px-2 py-1 uppercase"
                  @change="normalizeCorrBench"
                />
              </label>
              <button
                type="button"
                class="yf-range-item focus-ring"
                :data-selected="showCompMore"
                @click="showCompMore = !showCompMore"
              >
                {{ t("radar.comp_more") }}
              </button>
              <span v-if="peersLoading" class="text-caption1 text-ink-muted">{{ t("common.loading") }}</span>
            </div>
            <div class="yf-fin-scroll yf-comp-scroll">
              <table class="yf-fin-table yf-comp-table">
                <thead>
                  <tr>
                    <th>{{ t("radar.col_symbol") }}</th>
                    <th>{{ t("radar.col_spark") }}</th>
                    <th>{{ t("radar.col_price") }}</th>
                    <th>{{ t("radar.ret_1y") }}</th>
                    <th>{{ t("radar.vs_spy_1y") }}</th>
                    <th>{{ t("radar.col_beta60") }}</th>
                    <th>{{ t("radar.col_corr60") }}</th>
                    <th v-if="showCompMore">{{ t("radar.col_growth") }}</th>
                    <th v-if="showCompMore">{{ t("radar.col_gross") }}</th>
                    <th v-if="showCompMore">{{ t("radar.col_op_margin") }}</th>
                    <th v-if="showCompMore">{{ t("radar.col_pe") }}</th>
                    <th>{{ t("radar.drawdown") }}</th>
                    <th>{{ t("radar.col_mktcap") }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in peerTable" :key="row.ticker">
                    <th>
                      <button type="button" class="focus-ring font-display" @click="selectTicker(row.ticker)">
                        {{ row.ticker }}
                      </button>
                      <button
                        type="button"
                        class="ml-1 text-caption1 text-ink-muted focus-ring"
                        :title="t('radar.two_up')"
                        @click="setSecondary(row.ticker)"
                      >
                        {{ t("radar.two_up_short") }}
                      </button>
                      <div class="text-caption1 font-normal text-ink-muted">{{ row.sector || row.name || "" }}</div>
                    </th>
                    <td>
                      <QuoteSparkline :values="row.spark || []" :label="row.ticker" />
                    </td>
                    <td>{{ money(row.last) }}</td>
                    <td>{{ retLabel(row.ret_1y) }}</td>
                    <td>{{ retLabel(row.vs_spy_1y) }}</td>
                    <td>{{ row.beta60 != null ? number(row.beta60) : "—" }}</td>
                    <td>{{ row.corr60 != null ? number(row.corr60) : "—" }}</td>
                    <td v-if="showCompMore">{{ retLabel(row.revenue_growth) }}</td>
                    <td v-if="showCompMore">{{ retLabel(row.gross_margin) }}</td>
                    <td v-if="showCompMore">{{ retLabel(row.operating_margin) }}</td>
                    <td v-if="showCompMore">{{ number(row.pe_ratio) }}</td>
                    <td>{{ retLabel(row.drawdown_1y) }}</td>
                    <td>{{ money(row.market_cap, "USD", true) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section
            v-if="rrg.coords.length"
            id="market-rrg"
            class="mt-5"
            :aria-label="t('radar.rrg_label')"
            :data-focus="focusPanel === 'rrg'"
          >
            <h3 class="mb-2 text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.rrg_label") }}
            </h3>
            <div class="yf-rrg">
              <svg class="yf-rrg-svg" :viewBox="`0 0 ${rrg.size} ${rrg.size}`" role="img" :aria-label="t('radar.rrg_label')">
                <line :x1="rrg.mid" y1="8" :x2="rrg.mid" :y2="rrg.size - 8" stroke="rgb(var(--color-border-subtle))" />
                <line x1="8" :y1="rrg.mid" :x2="rrg.size - 8" :y2="rrg.mid" stroke="rgb(var(--color-border-subtle))" />
                <path
                  v-for="trail in rrgTrailLayout"
                  :key="`trail-${trail.ticker}`"
                  :d="trail.d"
                  class="yf-rrg-trail"
                  fill="none"
                />
                <g
                  v-for="point in rrg.coords"
                  :key="point.ticker"
                  class="yf-rrg-hit"
                  role="button"
                  tabindex="0"
                  @click="selectTicker(point.ticker)"
                  @keydown.enter.prevent="selectTicker(point.ticker)"
                >
                  <circle
                    :cx="point.cx"
                    :cy="point.cy"
                    r="5"
                    :fill="point.quadrant === 'leading' || point.quadrant === 'improving' ? 'rgb(var(--color-success))' : 'rgb(var(--color-danger))'"
                  />
                  <text
                    :x="point.cx + 7"
                    :y="point.cy + 3"
                    class="yf-rrg-label"
                  >
                    {{ point.ticker }}
                  </text>
                </g>
              </svg>
              <ul class="yf-rrg-legend">
                <li v-for="point in rrg.coords" :key="`q-${point.ticker}`">
                  <button type="button" class="focus-ring" @click="selectTicker(point.ticker)">
                    {{ point.ticker }}
                    <span class="text-ink-muted">{{ t(`radar.rrg_${point.quadrant}`) }}</span>
                  </button>
                </li>
              </ul>
            </div>
          </section>

          <div v-if="weekRangePct != null" class="mt-4">
            <div class="mb-1 flex justify-between text-caption1 text-ink-muted">
              <span>{{ t("radar.stat_52w") }}</span>
              <span>{{ weekRangeLabel(selected) }}</span>
            </div>
            <div class="yf-range-bar">
              <span class="yf-range-bar-fill" :style="{ left: `${weekRangePct}%` }"></span>
            </div>
          </div>

          <section
            v-if="earnStrip.nextDate || earnStrip.lastSurprise != null"
            class="yf-earn-strip mt-5"
            :aria-label="t('radar.earn_strip_label')"
          >
            <h3 class="mb-2 text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.earn_strip_label") }}
            </h3>
            <dl class="yf-stats">
              <div class="yf-stat">
                <dt>{{ t("radar.stat_next_earn") }}</dt>
                <dd>
                  {{ earnStrip.nextDate || "—" }}
                  <span v-if="earnStrip.nextEstimated" class="text-caption1 text-ink-muted">
                    {{ t("radar.earn_estimated") }}
                  </span>
                </dd>
              </div>
              <div class="yf-stat">
                <dt>{{ t("radar.earn_last_surprise") }}</dt>
                <dd :class="Number(earnStrip.lastSurprise) >= 0 ? 'text-success' : 'text-danger'">
                  {{ retLabel(earnStrip.lastSurprise) }}
                </dd>
              </div>
              <div class="yf-stat">
                <dt>{{ t("radar.earn_consensus") }}</dt>
                <dd>{{ earnStrip.consensus != null ? number(earnStrip.consensus) : "—" }}</dd>
              </div>
              <div class="yf-stat">
                <dt>{{ t("radar.earn_revisions") }}</dt>
                <dd>
                  {{
                    earnStrip.revisionsUp != null
                      ? t("radar.earn_rev_net", {
                          up: earnStrip.revisionsUp,
                          down: earnStrip.revisionsDown || 0,
                        })
                      : "—"
                  }}
                </dd>
              </div>
              <div v-if="earnStrip.avgSurprise != null" class="yf-stat">
                <dt>{{ t("radar.earn_avg_surprise") }}</dt>
                <dd>{{ retLabel(earnStrip.avgSurprise) }}</dd>
              </div>
            </dl>
          </section>

          <div class="mt-5">
            <button
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="showAllStats"
              @click="showAllStats = !showAllStats"
            >
              {{ t("radar.stats_toggle") }}
            </button>
            <dl v-if="showAllStats" class="yf-stats mt-3">
              <div v-for="stat in stats" :key="stat.label" class="yf-stat">
                <dt>{{ stat.label }}</dt>
                <dd>{{ stat.value }}</dd>
              </div>
            </dl>
          </div>

          <div id="market-workspace">
            <p class="mt-6 mb-2 text-caption1 text-ink-muted">{{ t("radar.workspace_tabs_hint") }}</p>
            <QuoteWorkspace
              class="mt-6"
              :ticker="selected.ticker"
              :workspace="workspace"
              :chart-points="chart?.points || []"
              :chart-range="chartRange"
              :currency="selected.currency"
              :loading="workspaceLoading"
              :tab="workspaceTab"
              :holder-mix="holderMixLabel"
              :quotes="quotes"
              :last-price="Number(selected.last)"
              @update:tab="workspaceTab = $event"
            />
          </div>

          <section
            id="market-filings"
            class="mt-5"
            :aria-label="t('radar.filings_label')"
            :data-focus="focusPanel === 'filings'"
          >
            <h3 class="mb-2 text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.filings_label") }}
            </h3>
            <div v-if="!selectedFilings.length" class="mb-3 flex flex-wrap gap-2">
              <a
                v-for="link in filingLinks"
                :key="link.id"
                :href="link.url"
                target="_blank"
                rel="noopener noreferrer"
                class="yf-range-item focus-ring"
              >
                {{ link.form }}
              </a>
            </div>
            <p v-if="!selectedFilings.length" class="text-footnote text-ink-muted">
              {{ t("radar.filings_empty") }}
            </p>
            <ul class="space-y-2">
              <li v-for="item in selectedFilings" :key="item.id">
                <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span v-if="item.form" class="text-caption1 font-semibold text-ink-muted">{{ item.form }}</span>
                  <a
                    v-if="item.url"
                    :href="item.url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-callout text-accent-ink focus-ring rounded-sm"
                  >
                    {{ item.title }}
                  </a>
                  <span v-else class="text-callout text-ink-primary">{{ item.title }}</span>
                  <span class="text-caption1 text-ink-muted">{{ radarAge(item.ts || item.captured_at, t) }}</span>
                </div>
                <p v-if="item.snip" class="mt-0.5 text-footnote text-ink-secondary">
                  {{ item.snip }}
                </p>
              </li>
            </ul>
          </section>

          <div class="mt-5 flex flex-wrap gap-2">
            <button
              v-if="openCopilot"
              type="button"
              class="btn-filled focus-ring"
              @click="openAsk"
            >
              {{ t("copilot.ask_short") }}
            </button>
            <button
              v-if="openCopilot"
              type="button"
              class="btn-bordered focus-ring"
              @click="askWhyMoving"
            >
              {{ t("radar.why_moving") }}
            </button>
            <button
              v-if="selected.companyId"
              type="button"
              class="btn-bordered focus-ring"
              @click="openCompany(selected)"
            >
              {{ t("radar.open_company") }}
            </button>
            <RouterLink class="btn-bordered focus-ring" :to="{ name: 'weekly-summary' }">
              {{ t("radar.open_pulse") }}
            </RouterLink>
            <RouterLink class="btn-bordered focus-ring" :to="{ name: 'research-page-market-pulse' }">
              {{ t("radar.open_signals") }}
            </RouterLink>
            <RouterLink class="btn-bordered focus-ring" :to="{ name: 'tracking' }">
              {{ t("radar.open_tracking") }}
            </RouterLink>
          </div>
        </article>

        <section
          id="market-calendar"
          class="news-grouped p-4"
          :aria-label="t('radar.calendar_label')"
          :data-focus="focusPanel === 'calendar'"
        >
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.calendar_label") }}
            </h3>
            <div class="flex items-center gap-2">
              <button
                v-if="upcomingEvents.length"
                type="button"
                class="yf-range-item focus-ring"
                @click="exportCalendar"
              >
                {{ t("radar.ics_export") }}
              </button>
              <span v-if="calendarLoading" class="text-caption1 text-ink-muted">{{ t("common.loading") }}</span>
            </div>
          </div>
          <div class="yf-chart-tools mb-3">
            <button
              v-for="item in calendarFilters"
              :key="item.id"
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="calendarFilter === item.id"
              @click="calendarFilter = item.id"
            >
              {{ item.label }}
            </button>
          </div>
          <div class="mb-3 flex flex-wrap gap-1">
            <button type="button" class="yf-range-item focus-ring" :data-selected="calendarView === 'list'" @click="calendarView = 'list'">
              {{ t("radar.cal_list") }}
            </button>
            <button type="button" class="yf-range-item focus-ring" :data-selected="calendarView === 'week'" @click="calendarView = 'week'">
              {{ t("radar.cal_week") }}
            </button>
          </div>
          <div v-if="calendarView === 'week'" class="yf-week-grid mb-3">
            <div v-for="day in weekGrid.days" :key="day.date" class="yf-week-day">
              <span class="yf-week-day-label">{{ day.label }} · {{ day.date.slice(5) }}</span>
              <button
                v-for="event in day.events.slice(0, 4)"
                :key="`${event.kind}-${event.ticker}-${event.title}`"
                type="button"
                class="yf-week-event mb-1 block w-full truncate text-left text-caption1 focus-ring"
                :data-kind="event.kind"
                @click="event.ticker && selectTicker(event.ticker)"
              >
                <span class="font-display">{{ event.ticker || event.kind }}</span>
                {{ eventTitle(event) }}
              </button>
            </div>
          </div>
          <p v-if="!upcomingEvents.length" class="text-callout text-ink-muted">
            {{ t("radar.calendar_empty") }}
          </p>
          <div v-else-if="calendarView === 'list'" class="yf-fin-scroll">
            <table class="yf-fin-table">
              <thead>
                <tr>
                  <th>{{ t("radar.col_date") }}</th>
                  <th>{{ t("radar.col_symbol") }}</th>
                  <th>{{ t("radar.col_event") }}</th>
                  <th>{{ t("radar.col_time") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="event in upcomingEvents" :key="`${event.kind}-${event.ticker || event.title}-${event.date}`">
                  <th>{{ event.date }}</th>
                  <td>
                    <button
                      v-if="event.ticker"
                      type="button"
                      class="focus-ring font-display"
                      @click="selectTicker(event.ticker)"
                    >
                      {{ event.ticker }}
                    </button>
                    <span v-else class="text-ink-muted">{{ event.name || "—" }}</span>
                  </td>
                  <td>
                    {{ eventTitle(event) }}
                    <span v-if="event.confirmed === false" class="text-caption1 text-ink-muted">
                      {{ t("radar.earn_estimated") }}
                    </span>
                  </td>
                  <td>{{ event.time || "—" }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section
          id="market-breadth"
          class="mb-4"
          :aria-label="t('radar.breadth_label')"
          :data-focus="focusPanel === 'breadth'"
        >
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.breadth_label") }}
            </h3>
            <QuoteSparkline
              v-if="breadthHistory.length"
              :values="breadthHistory"
              :label="t('radar.breadth_label')"
            />
          </div>
          <div class="yf-breadth">
            <span>{{ t("radar.breadth_adv", { n: breadth.advancers }) }}</span>
            <span>{{ t("radar.breadth_dec", { n: breadth.decliners }) }}</span>
            <span v-if="breadth.aboveSmaPct != null">
              {{ t("radar.breadth_sma", { n: breadth.aboveSmaPct.toFixed(0) }) }}
            </span>
            <span v-if="breadth.nearHighPct != null">
              {{ t("radar.breadth_highs", { n: breadth.nearHighPct.toFixed(0) }) }}
            </span>
          </div>
        </section>

        <section id="market-board">
          <div class="segmented mb-3" role="tablist" :aria-label="t('radar.board_label')">
            <button
              v-for="item in tabs"
              :key="item.id"
              type="button"
              class="segmented-item focus-ring"
              role="tab"
              :data-selected="tab === item.id"
              :aria-selected="tab === item.id"
              @click="tab = item.id"
            >
              {{ item.label }}
              <span class="yf-tab-count">{{ item.count }}</span>
            </button>
          </div>

          <div v-if="tab === 'watchlist'" class="mb-3 flex flex-wrap gap-1">
            <button
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="watchGroupFilter === 'all'"
              @click="watchGroupFilter = 'all'"
            >
              {{ t("radar.group_all") }}
            </button>
            <button
              v-for="group in WATCH_GROUPS"
              :key="`filt-${group}`"
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="watchGroupFilter === group"
              @click="watchGroupFilter = group"
            >
              {{ group }}
              <span class="yf-tab-count">{{ groupCount(group) }}</span>
            </button>
            <button
              v-for="id in WATCH_COLUMN_IDS"
              :key="id"
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="watchColSet.has(id)"
              @click="flipWatchColumn(id)"
            >
              {{ colLabel(id) }}
            </button>
          </div>

          <section
            v-if="heatRows.length && (tab === 'screener' || tab === 'gainers')"
            class="mb-4"
            :aria-label="t('radar.heat_label')"
          >
            <h3 class="mb-2 text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.heat_label") }}
            </h3>
            <div class="yf-heat">
              <button
                v-for="cell in heatRows"
                :key="cell.sector"
                type="button"
                class="yf-heat-cell focus-ring"
                :style="{ '--heat': heatTone(cell.avg) }"
                @click="openHeatCell(cell)"
              >
                <span class="yf-heat-name">{{ cell.sector }}</span>
                <span v-if="cell.leader?.ticker" class="yf-heat-leader font-display tabular">
                  {{ cell.leader.ticker }}
                </span>
                <span
                  class="yf-heat-avg tabular"
                  :class="cell.avg >= 0 ? 'text-success' : 'text-danger'"
                >
                  {{ signedChange(cell.avg) }}
                </span>
                <span class="yf-heat-count">{{ cell.count }}</span>
              </button>
            </div>
          </section>

          <div v-if="tab === 'screener'" class="yf-screener-filters mb-3">
            <div v-if="savedScreens.length" class="mb-2 flex flex-wrap gap-2">
              <button
                v-for="screen in savedScreens"
                :key="screen.id"
                type="button"
                class="yf-range-item focus-ring"
                @click="applySavedScreen(screen.id)"
                @dblclick="dropSavedScreen(screen.id)"
                :title="t('radar.eqs_delete_hint')"
              >
                {{ screen.name }}
              </button>
            </div>
            <label class="yf-screener-field">
              <span>{{ t("radar.filter_sector") }}</span>
              <select v-model="screenerSector" class="focus-ring">
                <option value="">{{ t("radar.filter_any") }}</option>
                <option v-for="sector in (screeners.sectors || [])" :key="sector" :value="sector">
                  {{ sector }}
                </option>
              </select>
            </label>
            <label class="yf-screener-field">
              <span>{{ t("radar.filter_cap") }}</span>
              <select v-model="screenerCap" class="focus-ring">
                <option value="">{{ t("radar.filter_any") }}</option>
                <option value="mega">{{ t("radar.cap_mega") }}</option>
                <option value="large">{{ t("radar.cap_large") }}</option>
                <option value="mid">{{ t("radar.cap_mid") }}</option>
                <option value="small">{{ t("radar.cap_small") }}</option>
              </select>
            </label>
            <label class="yf-screener-field">
              <span>{{ t("radar.filter_min_change") }}</span>
              <input v-model="screenerMinChange" type="number" step="0.5" class="focus-ring" :placeholder="t('radar.filter_min_change_ph')" />
            </label>
            <label class="yf-screener-field">
              <span>{{ t("radar.filter_min_volume") }}</span>
              <input v-model="screenerMinVolume" type="number" step="100000" class="focus-ring" :placeholder="t('radar.filter_min_volume_ph')" />
            </label>
            <label class="yf-screener-field yf-screener-field-wide">
              <span>{{ t("radar.filter_query") }}</span>
              <input v-model="screenerQuery" type="search" class="focus-ring" :placeholder="t('radar.filter_query_ph')" />
            </label>
            <form class="yf-screener-field yf-screener-field-wide flex items-end gap-2" @submit.prevent="persistCurrentScreen">
              <label class="min-w-0 flex-1">
                <span>{{ t("radar.eqs_save") }}</span>
                <input v-model="screenNameDraft" type="text" class="focus-ring" :placeholder="t('radar.eqs_save_ph')" />
              </label>
              <button type="submit" class="yf-range-item focus-ring mb-0.5">{{ t("radar.eqs_save_btn") }}</button>
              <button type="button" class="yf-range-item focus-ring mb-0.5" @click="shareScreenUrl">
                {{ t("radar.eqs_share") }}
              </button>
            </form>
          </div>

          <div class="news-grouped overflow-hidden">
            <div
              class="yf-table-head"
              :class="tab === 'watchlist' ? 'yf-table-head-flex' : tab === 'screener' ? 'yf-table-head-eqs' : 'yf-table-head-wide'"
              :style="tab === 'watchlist' ? boardGridStyle : undefined"
            >
              <span>{{ t("radar.col_symbol") }}</span>
              <template v-if="tab === 'watchlist'">
                <span v-for="id in watchColumns" :key="id" class="text-right">{{ colLabel(id) }}</span>
              </template>
              <template v-else-if="tab === 'screener'">
                <span class="text-right">{{ t("radar.col_price") }}</span>
                <span class="text-right">{{ t("radar.col_change") }}</span>
                <span class="text-right">{{ t("radar.col_rsi") }}</span>
                <span class="text-right">{{ t("radar.col_vol_ratio") }}</span>
                <span class="text-right">{{ t("radar.col_next_earn") }}</span>
              </template>
              <template v-else>
                <span class="text-right">{{ t("radar.col_price") }}</span>
                <span class="text-right">{{ t("radar.col_change") }}</span>
                <span class="text-right">{{ t("radar.col_volume") }}</span>
              </template>
            </div>
            <p
              v-if="displayBoardRows.length === 0"
              class="px-4 py-8 text-center text-callout text-ink-muted"
            >
              {{ t("radar.board_empty") }}
            </p>
            <button
              v-for="row in displayBoardRows"
              :key="row.ticker"
              type="button"
              class="yf-table-row focus-ring"
              :class="tab === 'watchlist' ? 'yf-table-head-flex' : tab === 'screener' ? 'yf-table-row-eqs' : 'yf-table-row-wide'"
              :style="tab === 'watchlist' ? boardGridStyle : undefined"
              :data-selected="selected?.ticker === row.ticker"
              @click="selectRow(row)"
              @dblclick="openCompany(row)"
              @contextmenu.prevent="openGroupMenu(row)"
            >
              <span class="min-w-0 text-left">
                <span class="block font-display text-headline tabular text-ink-primary">
                  {{ row.ticker }}
                </span>
                <span class="block truncate text-caption1 text-ink-muted">
                  {{ row.name }}
                </span>
                <span
                  v-if="tab === 'watchlist' && row.group"
                  class="mt-0.5 block text-caption1 text-ink-subtle"
                >
                  {{ row.group }}
                </span>
                <div
                  v-if="tab === 'watchlist' && groupMenuTicker === row.ticker"
                  class="yf-group-menu mt-1 flex flex-wrap gap-1"
                  @click.stop
                >
                  <button
                    v-for="group in WATCH_GROUPS"
                    :key="`gm-${row.ticker}-${group}`"
                    type="button"
                    class="yf-range-item focus-ring"
                    :data-selected="pinGroupFor(row.ticker, pinGroups) === group"
                    @click="assignRowGroup(row.ticker, group)"
                  >
                    {{ group }}
                  </button>
                  <button type="button" class="yf-range-item focus-ring" @click="groupMenuTicker = ''">
                    {{ t("cmd.esc") }}
                  </button>
                </div>
              </span>
              <template v-if="tab === 'watchlist'">
                <span
                  v-for="id in watchColumns"
                  :key="`${row.ticker}-${id}`"
                  class="mono-data text-right text-caption1 tabular"
                  :class="id === 'change' && row.change != null ? (row.change >= 0 ? 'text-success' : 'text-danger') : 'text-ink-primary'"
                >
                  {{ cellValue(row, id) }}
                </span>
              </template>
              <template v-else-if="tab === 'screener'">
                <span class="mono-data text-right text-footnote tabular text-ink-primary">
                  {{ priceLabel(row) }}
                </span>
                <span class="text-right">
                  <span
                    v-if="row.change != null"
                    class="inline-flex rounded-md px-1.5 py-0.5 text-caption1 font-semibold tabular"
                    :class="row.change >= 0 ? 'bg-success-soft text-success-ink' : 'bg-danger-soft text-danger-ink'"
                  >
                    {{ signedChange(row.change) }}
                  </span>
                  <span v-else class="text-caption1 text-ink-subtle">—</span>
                </span>
                <span class="mono-data text-right text-caption1 tabular text-ink-muted">
                  {{ row.rsi != null ? number(row.rsi) : "—" }}
                </span>
                <span class="mono-data text-right text-caption1 tabular text-ink-muted">
                  {{ row.volRatio != null ? `${row.volRatio.toFixed(1)}×` : "—" }}
                </span>
                <span class="mono-data text-right text-caption1 tabular text-ink-muted">
                  {{ row.earnDays != null ? t("radar.earn_days", { n: row.earnDays }) : "—" }}
                </span>
              </template>
              <template v-else>
                <span class="mono-data text-right text-footnote tabular text-ink-primary">
                  {{ priceLabel(row) }}
                </span>
                <span class="text-right">
                  <span
                    v-if="row.change != null"
                    class="inline-flex rounded-md px-1.5 py-0.5 text-caption1 font-semibold tabular"
                    :class="row.change >= 0 ? 'bg-success-soft text-success-ink' : 'bg-danger-soft text-danger-ink'"
                  >
                    {{ signedChange(row.change) }}
                  </span>
                  <span v-else class="text-caption1 text-ink-subtle">—</span>
                </span>
                <span class="mono-data text-right text-caption1 tabular text-ink-muted">
                  {{ compact(row.volume) }}
                </span>
              </template>
            </button>
          </div>
        </section>
      </div>

      <aside
        class="items-start gap-4"
        :class="
          deskExpanded
            ? 'grid lg:grid-cols-2'
            : 'space-y-4 lg:sticky lg:top-4 lg:col-span-4 lg:self-start'
        "
      >
        <section
          v-if="bookLots.length"
          id="market-risk"
          class="news-grouped px-4 py-3"
          :aria-label="t('radar.risk_label')"
          :data-focus="focusPanel === 'risk'"
        >
          <div class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
            {{ t("radar.risk_label") }}
          </div>
          <p v-if="bookRisk.portfolioBeta != null" class="mt-1 text-footnote">
            {{ t("radar.risk_beta", { n: bookRisk.portfolioBeta.toFixed(2) }) }}
          </p>
          <p v-if="bookRisk.spyEquivalent != null" class="text-caption1 text-ink-muted">
            {{ t("radar.risk_spy_eq", { n: money(bookRisk.spyEquivalent, "USD", true) }) }}
          </p>
          <p v-if="bookRisk.expectedDayPct != null" class="text-caption1" :class="bookRisk.expectedDayPct >= 0 ? 'text-success' : 'text-danger'">
            {{ t("radar.risk_expected", { n: signedChange(bookRisk.expectedDayPct) }) }}
          </p>
          <p v-else class="mt-1 text-caption1 text-ink-muted">{{ t("radar.risk_empty") }}</p>
          <div
            v-if="bookPnlView.rows.length"
            class="mt-3 border-t border-[rgb(var(--color-border-subtle))] pt-2"
            data-testid="book-pnl"
          >
            <div class="flex items-baseline justify-between gap-2">
              <span class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
                {{ t("radar.pnl_label") }}
              </span>
              <span class="mono-data text-footnote tabular text-ink-primary">
                {{ money(bookPnlView.marketValue, "USD", true) }}
              </span>
            </div>
            <p class="mt-0.5 text-caption1">
              <span :class="bookPnlView.dayPnl >= 0 ? 'text-success' : 'text-danger'">
                {{ t("radar.pnl_day", { n: money(bookPnlView.dayPnl, "USD", true) }) }}
              </span>
              <span class="mx-1 text-ink-subtle">·</span>
              <span :class="bookPnlView.unrealized >= 0 ? 'text-success' : 'text-danger'">
                {{ t("radar.pnl_unrealized", { n: money(bookPnlView.unrealized, "USD", true) }) }}
              </span>
            </p>
            <div class="mt-1.5 space-y-0.5">
              <button
                v-for="row in bookPnlView.rows.slice(0, 6)"
                :key="`pnl-${row.ticker}`"
                type="button"
                class="flex w-full items-center justify-between gap-2 rounded-sm text-left focus-ring"
                @click="selectTicker(row.ticker, row.companyId)"
              >
                <span class="font-display text-footnote tabular">
                  {{ row.ticker }}
                  <span class="ml-1 text-caption1 font-normal text-ink-muted">×{{ row.shares }}</span>
                </span>
                <span
                  class="mono-data text-caption1 tabular"
                  :class="(row.dayPnl ?? 0) >= 0 ? 'text-success' : 'text-danger'"
                >
                  {{ row.dayPnl != null ? money(row.dayPnl, "USD", true) : "—" }}
                </span>
              </button>
            </div>
          </div>
        </section>

        <section
          v-if="trackedCompanies.length"
          class="news-grouped px-4 py-3"
          :aria-label="t('radar.book_lens_label')"
        >
          <div class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
            {{ t("radar.book_lens_label") }}
          </div>
          <p v-if="bookLens.avgBeta != null" class="mt-1 text-footnote text-ink-secondary">
            {{ t("radar.book_beta", { n: bookLens.avgBeta.toFixed(2) }) }}
          </p>
          <div v-if="bookLens.sectorMix.length" class="mt-2 flex flex-wrap gap-1">
            <span
              v-for="row in bookLens.sectorMix.slice(0, 4)"
              :key="row.sector"
              class="text-caption1 text-ink-muted"
            >
              {{ row.sector }} {{ row.pct.toFixed(0) }}%
            </span>
          </div>
          <div class="mt-2 space-y-1">
            <button
              v-for="row in bookLens.movers.slice(0, 4)"
              :key="row.ticker"
              type="button"
              class="flex w-full items-center justify-between gap-2 text-left focus-ring rounded-sm"
              @click="selectTicker(row.ticker, row.companyId)"
            >
              <span class="font-display text-footnote tabular">{{ row.ticker }}</span>
              <span
                class="mono-data text-caption1 tabular"
                :class="row.change >= 0 ? 'text-success' : 'text-danger'"
              >
                {{ signedChange(row.change) }}
              </span>
            </button>
          </div>
        </section>

        <section
          id="market-news"
          class="news-grouped overflow-hidden"
          :class="deskExpanded ? 'lg:col-span-2' : ''"
          :data-focus="focusPanel === 'news'"
        >
          <div class="flex items-center justify-between gap-2 px-4 pb-1 pt-3">
            <h2 class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {{ t("radar.tape_label") }}
            </h2>
            <div class="flex items-center gap-2">
              <button
                v-if="openCopilot"
                type="button"
                class="text-caption1 font-medium text-accent-ink focus-ring rounded-pill px-1"
                @click="openAsk"
              >
                {{ t("copilot.ask_short") }}
              </button>
              <button
                v-if="openCopilot"
                type="button"
                class="text-caption1 font-medium text-accent-ink focus-ring rounded-pill px-1"
                @click="askWhyMoving"
              >
                {{ t("radar.why_moving") }}
              </button>
              <RouterLink
                class="text-caption1 font-medium text-accent-ink focus-ring rounded-pill px-1"
                :to="{ name: 'news-desk' }"
              >
                {{ t("radar.open_news") }}
              </RouterLink>
            </div>
          </div>
          <div class="border-b border-[rgb(var(--color-border-subtle))] px-4 pb-3">
            <div v-if="pulseLoading" class="flex items-center gap-2 text-callout text-ink-muted">
              <Loader2 class="h-4 w-4 animate-spin" />
              {{ t("common.loading") }}
            </div>
            <p v-else-if="pulseError" class="text-callout text-danger">{{ pulseError }}</p>
            <template v-else>
              <p class="text-headline text-ink-primary">{{ postureLabel }}</p>
              <p class="mt-1 text-footnote text-ink-secondary">
                {{
                  t("home.desk_breadth", {
                    up: regime.breadth?.positive_signals || 0,
                    down: regime.breadth?.negative_signals || 0,
                    flat: regime.breadth?.neutral_signals || 0,
                  })
                }}
              </p>
              <p v-if="topSignal" class="mt-2 text-callout text-ink-primary">
                {{ topSignal }}
              </p>
            </template>
          </div>
          <div class="flex flex-wrap gap-1 px-4 py-2">
            <button
              v-for="scope in [
                { id: 'all', label: t('radar.news_all') },
                { id: 'book', label: t('radar.news_book') },
                { id: 'filings', label: t('radar.news_filings') },
              ]"
              :key="scope.id"
              type="button"
              class="yf-range-item focus-ring"
              :data-selected="newsScope === scope.id"
              @click="newsScope = scope.id"
            >
              {{ scope.label }}
            </button>
          </div>
          <p v-if="loadingFeed && !selectedHeadlines.length" class="px-4 py-5 text-callout text-ink-muted">
            {{ t("common.loading") }}
          </p>
          <p v-else-if="!selectedHeadlines.length" class="px-4 py-5 text-callout text-ink-muted">
      {{ t("toolbar.radar_empty") }}
    </p>
          <div :class="deskExpanded ? 'lg:grid lg:grid-cols-2' : ''">
      <RouterLink
              v-for="item in selectedHeadlines"
        :key="item.id"
        :to="radarRoute(item)"
              class="news-story-row focus-ring"
      >
              <Newspaper class="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" />
        <span class="min-w-0 flex-1">
                <span class="block text-headline text-ink-primary">
                  {{ item.title || t("sidebar.untitled") }}
                </span>
                <span class="block text-caption1 text-ink-muted">
                  <span v-if="item.category === 'filings'" class="mr-1">{{ t("radar.news_filings") }} ·</span>
                  {{ radarAge(item.captured_at || item.ts, t) }}
                  <template v-if="reactionFor(item)">
                    <span class="mx-1">·</span>
                    <span
                      class="mono-data font-semibold tabular"
                      :class="reactionFor(item).pct >= 0 ? 'text-success' : 'text-danger'"
                    >
                      {{ reactionFor(item).ticker }} {{ signedChange(reactionFor(item).pct) }}
                      {{ t("radar.reaction_since") }}
                    </span>
                  </template>
                </span>
        </span>
      </RouterLink>
    </div>
        </section>
      </aside>
    </div>
    <div v-if="shareToast" class="yf-toast" role="status">{{ shareToast }}</div>
  </div>
</template>
