/** Workspace front-desk helpers: normalize, classify, and filter news. */

const MARKET_RE =
  /\b(fed|fomc|treasury|treasuries|inflation|cpi|ppi|rates?|yields?|macro|s&p|nasdaq|dow\b|oil|brent|wti|volatility|vix|sector|breadth|risk[- ]on|risk[- ]off|equities|bond market)\b/i;

const CATEGORY_ALIASES = {
  filings: "filings",
  filing: "filings",
  sec: "filings",
  earnings: "filings",
  funding: "funding",
  fundraising: "funding",
  financing: "funding",
  partnership: "press",
  product: "product",
  press: "press",
  research: "research",
};

export function newsTitle(item) {
  return String(item?.title || item?.headline || "").trim();
}

export function newsTimestamp(item) {
  return String(
    item?.published_at ||
      item?.captured_at ||
      item?.date ||
      item?.created_at ||
      "",
  );
}

export function newsHaystack(item) {
  return [
    newsTitle(item),
    item?.summary,
    item?.company,
    item?.ticker,
    item?.source,
    item?.domain,
    item?.category,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

/** Local company archive rows older than this are dropped once live headlines exist. */
export const MAX_ARCHIVE_AGE_DAYS = 14;

function parseNewsTime(ts) {
  const stamp = Date.parse(ts);
  return Number.isFinite(stamp) ? stamp : null;
}

export function inferNewsCategory(item) {
  const explicit = String(item?.category || item?.tag || "").toLowerCase();
  if (CATEGORY_ALIASES[explicit]) return CATEGORY_ALIASES[explicit];
  if (item?.kind === "external_research") return "research";
  const hay = newsHaystack(item);
  if (/\b(10-k|10-q|8-k|s-1|sec filing|earnings|13f)\b/.test(hay)) return "filings";
  if (/\b(series [a-z]|raises?|funding|valuation|ipo|financing)\b/.test(hay)) {
    return "funding";
  }
  if (/\b(launch|product|release|platform|chip|foundry)\b/.test(hay)) {
    return "product";
  }
  return "press";
}

// Headlines say "Intel", not "Intel Corp", and "Amgen", not "Amgen Inc": a
// match on the full legal name alone missed nearly every story. Suffixes are
// dropped (repeatedly: "Holdings Inc."), and names and tickers must match as
// whole words, so "nb" no longer matches inside "nba" or "amd" inside "amdocs".
const NAME_SUFFIX_RE =
  /[,\s]+(incorporated|inc\.?|corporation|corp\.?|company|co\.?|ltd\.?|limited|plc|llc|l\.?p\.?|holdings?|group|n\.v\.|s\.a\.|ag|se)$/i;

export function companyNameKeys(company) {
  const full = String(company?.name || "").trim().toLowerCase();
  const keys = new Set();
  if (full.length >= 3) keys.add(full);
  let short = full;
  for (let i = 0; i < 3; i += 1) {
    const next = short.replace(NAME_SUFFIX_RE, "").trim();
    if (next === short) break;
    short = next;
  }
  if (short.length >= 3) keys.add(short);
  return [...keys];
}

function containsWord(hay, needle) {
  if (!needle) return false;
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z0-9])${escaped}($|[^a-z0-9])`).test(hay);
}

export function matchCompaniesForNews(item, companies = []) {
  const assigned =
    item?.company_id ||
    item?.intake_assignment?.company_id ||
    item?.matched_company_id;
  const hits = [];
  const seen = new Set();
  const push = (company) => {
    if (!company?.id || seen.has(String(company.id))) return;
    seen.add(String(company.id));
    hits.push(company);
  };
  if (assigned) {
    const row = companies.find((c) => String(c.id) === String(assigned));
    if (row) push(row);
  }
  const itemTicker = String(item?.ticker || "")
    .trim()
    .toUpperCase();
  if (itemTicker) {
    const byTicker = companies.find(
      (c) => String(c?.ticker || "").trim().toUpperCase() === itemTicker,
    );
    if (byTicker) push(byTicker);
  }
  const hay = newsHaystack(item);
  for (const company of companies) {
    const ticker = String(company?.ticker || "").trim().toLowerCase();
    if (companyNameKeys(company).some((key) => containsWord(hay, key))) push(company);
    if (ticker && containsWord(hay, ticker)) push(company);
  }
  return hits;
}

export function isMarketNews(item, matchedCompanies = []) {
  if (matchedCompanies.length) return false;
  return MARKET_RE.test(newsHaystack(item));
}

function makeRow(item, companies, extras = {}) {
  const matched = extras.matched || matchCompaniesForNews(item, companies);
  const category = extras.category || inferNewsCategory(item);
  const kind = extras.kind || item.kind || "news";
  const ticker = String(
    extras.ticker || item.ticker || matched[0]?.ticker || "",
  )
    .trim()
    .toUpperCase();
  const companyName = String(
    extras.companyName || matched[0]?.name || item.company || "",
  ).trim();
  const marketDefault =
    kind === "live_news" ? matched.length === 0 : isMarketNews(item, matched);
  return {
    id: String(extras.id || item.id || ""),
    title: newsTitle(item),
    summary: String(item.summary || item.description || "").trim(),
    source: String(item.source || item.domain || item.kind || "").trim(),
    url: String(item.source_url || item.url || "").trim(),
    ts: newsTimestamp(item),
    category,
    kind,
    market: Boolean(extras.market ?? marketDefault),
    ticker,
    companyName,
    companies: matched,
    companyIds: matched.map((c) => String(c.id)),
    raw: item,
  };
}

export function normalizeFeedItem(item, companies = []) {
  if (!item?.id) return null;
  const title = newsTitle(item);
  if (!title) return null;
  const matched = matchCompaniesForNews(item, companies);
  return makeRow(item, companies, {
    id: `${item.kind || "news"}:${item.id}`,
    matched,
    kind: item.kind || "news",
  });
}

export function normalizeCompanyNews(company, item, index = 0) {
  if (!company?.id) return null;
  const title = newsTitle(item);
  if (!title) return null;
  const url = String(item.url || item.source_url || "").trim();
  const id = url
    ? `company:${company.id}:${url}`
    : `company:${company.id}:${title}:${item.published_at || item.date || index}`;
  return makeRow(
    {
      ...item,
      title,
      company_id: company.id,
      company: company.name,
      ticker: company.ticker,
    },
    [company],
    {
      id,
      matched: [company],
      kind: "company_news",
      market: false,
      companyName: company.name,
      ticker: company.ticker,
    },
  );
}

export function normalizeLiveNews(item, companies = []) {
  const title = newsTitle(item);
  if (!title) return null;
  const matched = matchCompaniesForNews(item, companies);
  const rawId = String(item.id || "").trim();
  return makeRow(item, companies, {
    id: rawId ? (rawId.startsWith("live:") ? rawId : `live:${rawId}`) : `live:${title}`,
    matched,
    kind: item.kind || "live_news",
    category: item.category || "markets",
    market: matched.length === 0,
  });
}

function isFreshArchiveRow(row, { hasLive = false, now = Date.now() } = {}) {
  const stamp = parseNewsTime(row?.ts);
  if (stamp == null) {
    // Undated archive rows only survive when nothing live is in.
    return !hasLive;
  }
  if (!hasLive) return true;
  const cutoff = now - MAX_ARCHIVE_AGE_DAYS * 24 * 60 * 60 * 1000;
  return stamp >= cutoff;
}

/**
 * `focusCompanyId` narrows the desk to one company (the sidebar's company
 * menu → News). Its own stored news is then kept however old it is — that
 * archive is the company's news page — and the cap applies after the
 * narrowing, so a busy tape cannot crowd the company's rows out.
 */
export function assembleDeskNews({
  feed = [],
  companies = [],
  live = [],
  limit = 100,
  now = Date.now(),
  focusCompanyId = "",
} = {}) {
  const focus = String(focusCompanyId || "");
  const liveRows = (live || [])
    .map((item) => normalizeLiveNews(item, companies))
    .filter(Boolean);
  const hasLive = liveRows.length > 0;
  const feedRows = (feed || [])
    .map((item) => normalizeFeedItem(item, companies))
    .filter(Boolean);
  const companyRows = [];
  for (const company of companies || []) {
    const local =
      Array.isArray(company.company_news) && company.company_news.length
        ? company.company_news
        : company.recent_news || [];
    const keepAll = focus && String(company.id) === focus;
    local.forEach((item, index) => {
      const row = normalizeCompanyNews(company, item, index);
      if (row && (keepAll || isFreshArchiveRow(row, { hasLive, now }))) companyRows.push(row);
    });
  }

  const candidates = [...liveRows, ...feedRows, ...companyRows]
    .filter((row) => !focus || row.companyIds.includes(focus))
    .sort((a, b) => String(b.ts || "").localeCompare(String(a.ts || "")));
  const rows = [];
  const seen = new Set();
  for (const row of candidates) {
    if (!row?.title) continue;
    const titleKey = row.title.toLowerCase();
    if (seen.has(titleKey) || seen.has(row.id)) continue;
    const key = `${row.url || ""}|${row.title}|${row.companyIds[0] || ""}`;
    if (seen.has(key)) continue;
    seen.add(titleKey);
    seen.add(row.id);
    seen.add(key);
    rows.push(row);
    if (rows.length >= limit) break;
  }
  return rows;
}

export function filterDeskNews(
  rows = [],
  { scope = "all", category = "", query = "", bookIds = [] } = {},
) {
  const book = new Set((bookIds || []).map(String));
  const q = String(query || "").trim().toLowerCase();
  return rows.filter((row) => {
    if (category && row.category !== category) return false;
    if (scope === "book") {
      if (!row.companyIds.some((id) => book.has(id))) return false;
    } else if (scope === "market") {
      if (!row.market) return false;
    }
    if (!q) return true;
    const hay = `${row.title} ${row.summary} ${row.source}`.toLowerCase();
    return hay.includes(q);
  });
}

/** Stable hash so lead/thumbnail tones match across renders (iOS-style). */
export function newsToneIndex(seed = "", size = 6) {
  const text = String(seed || "");
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) | 0;
  }
  return Math.abs(hash) % Math.max(1, size);
}

/** iOS system palette used by NewsLeadCard / NewsThumbnail. */
export const NEWS_TONE_KEYS = [
  "blue",
  "indigo",
  "purple",
  "teal",
  "orange",
  "pink",
  "mint",
];

export function newsToneKey(seed = "", { withMint = false } = {}) {
  const keys = withMint ? NEWS_TONE_KEYS : NEWS_TONE_KEYS.slice(0, 6);
  return keys[newsToneIndex(seed, keys.length)];
}

export function newsAgeParts(ts, now = Date.now()) {
  const stamp = Date.parse(ts);
  if (!Number.isFinite(stamp)) return null;
  const sec = Math.max(0, Math.round((now - stamp) / 1000));
  if (sec < 60) return { unit: "now", n: 0 };
  if (sec < 3600) return { unit: "minutes", n: Math.round(sec / 60) };
  if (sec < 86400) return { unit: "hours", n: Math.round(sec / 3600) };
  return { unit: "days", n: Math.round(sec / 86400) };
}

export function quoteMovers(companies = [], quotes = {}, limit = 6) {
  const rows = [];
  for (const company of companies) {
    const ticker = String(company?.ticker || "").trim().toUpperCase();
    if (!ticker) continue;
    const quote = quotes[ticker];
    const change = Number(quote?.change_pct_1d);
    if (!Number.isFinite(change)) continue;
    rows.push({
      id: company.id,
      name: company.name,
      ticker,
      change,
      last: quote.last_price,
      currency: quote.currency || "USD",
    });
  }
  rows.sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
  return rows.slice(0, limit);
}

/** ETF proxies for broad market boards (real quotes via /api/quotes). */
export const MARKET_INDEX_TICKERS = [
  { ticker: "SPY", label: "S&P 500" },
  { ticker: "QQQ", label: "Nasdaq 100" },
  { ticker: "DIA", label: "Dow 30" },
  { ticker: "IWM", label: "Russell 2000" },
  { ticker: "EFA", label: "Developed" },
  { ticker: "EEM", label: "Emerging" },
  { ticker: "GLD", label: "Gold" },
  { ticker: "USO", label: "Oil" },
  { ticker: "TLT", label: "Bonds" },
  { ticker: "VIXY", label: "VIX" },
  { ticker: "UUP", label: "USD" },
  { ticker: "HYG", label: "HY credit" },
];

/** WEI-style macro strip (subset of index defs). */
export const WEI_TICKERS = ["SPY", "QQQ", "TLT", "UUP", "USO", "VIXY", "HYG", "GLD"];

export const CHART_RANGES = ["1d", "5d", "1mo", "6mo", "ytd", "1y", "5y", "max"];

export function quoteBoardRows(quotes = {}, companies = []) {
  const byTicker = new Map();
  for (const company of companies) {
    const ticker = String(company?.ticker || "").trim().toUpperCase();
    if (ticker) byTicker.set(ticker, company);
  }
  const rows = [];
  for (const [ticker, quote] of Object.entries(quotes || {})) {
    const symbol = String(ticker || "").trim().toUpperCase();
    if (!symbol || !quote) continue;
    const change = Number(quote.change_pct_1d);
    const last = Number(quote.last_price);
    if (!Number.isFinite(last)) continue;
    const company = byTicker.get(symbol);
    rows.push({
      id: company?.id || symbol,
      companyId: company?.id || null,
      name: company?.name || quote.name || symbol,
      ticker: symbol,
      change: Number.isFinite(change) ? change : null,
      last,
      currency: quote.currency || "USD",
      asOf: quote.as_of || null,
      source: quote.source || null,
      volume: Number.isFinite(Number(quote.volume)) ? Number(quote.volume) : null,
      exchange: quote.exchange || null,
    });
  }
  return rows;
}

export function quoteGainers(rows = [], limit = 10) {
  return [...rows]
    .filter((row) => Number.isFinite(row.change) && row.change > 0)
    .sort((a, b) => b.change - a.change)
    .slice(0, limit);
}

export function quoteLosers(rows = [], limit = 10) {
  return [...rows]
    .filter((row) => Number.isFinite(row.change) && row.change < 0)
    .sort((a, b) => a.change - b.change)
    .slice(0, limit);
}

export function quoteMostActive(rows = [], limit = 10) {
  return [...rows]
    .filter((row) => Number.isFinite(row.volume) && row.volume > 0)
    .sort((a, b) => b.volume - a.volume)
    .slice(0, limit);
}

export function lookupQuoteMatches(query, companies = []) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return [];
  const rows = [];
  const seen = new Set();
  const tickerGuess = q.replace(/\s+/g, "").toUpperCase();
  const looksLikeTicker = /^[A-Z][A-Z0-9.-]{0,9}$/.test(tickerGuess);
  for (const company of companies) {
    const ticker = String(company?.ticker || "").trim().toUpperCase();
    const name = String(company?.name || "").trim();
    const hay = `${ticker} ${name}`.toLowerCase();
    if (!hay.includes(q)) continue;
    const key = ticker || String(company.id);
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({
      ticker: ticker || null,
      name,
      companyId: company.id,
      kind: "company",
    });
    if (rows.length >= 8) break;
  }
  if (looksLikeTicker && !seen.has(tickerGuess) && rows.length === 0) {
    rows.push({
      ticker: tickerGuess,
      name: tickerGuess,
      companyId: null,
      kind: "ticker",
    });
  }
  return rows;
}

export function indexQuoteCards(quotes = {}, defs = MARKET_INDEX_TICKERS) {
  return defs.map((def) => {
    const quote = quotes[def.ticker] || null;
    const change = Number(quote?.change_pct_1d);
    const last = Number(quote?.last_price);
    return {
      ticker: def.ticker,
      label: def.label,
      last: Number.isFinite(last) ? last : null,
      change: Number.isFinite(change) ? change : null,
      currency: quote?.currency || "USD",
      asOf: quote?.as_of || null,
    };
  });
}

const CAP_BANDS = {
  mega: [200e9, Infinity],
  large: [10e9, 200e9],
  mid: [2e9, 10e9],
  small: [0, 2e9],
};

export function filterScreenerRows(
  rows = [],
  {
    sector = "",
    cap = "",
    minChange = null,
    maxChange = null,
    minVolume = null,
    query = "",
    limit = 40,
  } = {},
) {
  const q = String(query || "").trim().toLowerCase();
  const band = CAP_BANDS[cap] || null;
  const filtered = (rows || []).filter((row) => {
    if (sector && row.sector !== sector) return false;
    if (band) {
      const mcap = Number(row.market_cap);
      if (!Number.isFinite(mcap) || mcap < band[0] || mcap >= band[1]) return false;
    }
    const change = Number(row.change_pct);
    if (minChange != null && Number.isFinite(Number(minChange))) {
      if (!Number.isFinite(change) || change < Number(minChange)) return false;
    }
    if (maxChange != null && Number.isFinite(Number(maxChange))) {
      if (!Number.isFinite(change) || change > Number(maxChange)) return false;
    }
    if (minVolume != null && Number.isFinite(Number(minVolume))) {
      const volume = Number(row.volume);
      if (!Number.isFinite(volume) || volume < Number(minVolume)) return false;
    }
    if (q) {
      const hay = `${row.ticker || ""} ${row.name || ""} ${row.sector || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  return filtered
    .sort((a, b) => (Number(b.market_cap) || 0) - (Number(a.market_cap) || 0))
    .slice(0, limit);
}

export function headlinesForTicker(items = [], { ticker = "", name = "", companies = [] } = {}) {
  const symbol = String(ticker || "").trim().toLowerCase();
  const label = String(name || "").trim().toLowerCase();
  const companyIds = new Set(
    (companies || [])
      .filter((row) => String(row?.ticker || "").trim().toUpperCase() === String(ticker || "").trim().toUpperCase())
      .map((row) => String(row.id)),
  );
  const matched = [];
  const rest = [];
  for (const item of items || []) {
    const hay = `${item.title || ""} ${item.summary || ""}`.toLowerCase();
    const byCompany =
      companyIds.size > 0 &&
      (item.companyIds || []).some((id) => companyIds.has(String(id)));
    const byText =
      (symbol && hay.includes(symbol)) ||
      (label && label.length > 3 && hay.includes(label));
    if (byCompany || byText) matched.push(item);
    else rest.push(item);
  }
  return (matched.length ? matched : rest).slice(0, 12);
}

/** Collapse near-duplicate headlines (same title stem / URL host). */
export function collapseDuplicateNews(rows = []) {
  const seen = new Set();
  const out = [];
  for (const row of rows || []) {
    const title = String(row?.title || "")
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fff]+/g, " ")
      .trim()
      .slice(0, 48);
    const host = String(row?.url || "")
      .replace(/^https?:\/\//i, "")
      .split("/")[0]
      .toLowerCase();
    const key = `${title}|${host}`;
    if (!title || seen.has(key) || seen.has(title)) continue;
    seen.add(key);
    seen.add(title);
    out.push(row);
  }
  return out;
}

/**
 * CN-style ranked news: book boost, ticker hit, filings weight, freshness.
 * Prefer Chinese title when lang === "zh".
 */
export function rankDeskNews(
  rows = [],
  { bookIds = [], ticker = "", name = "", lang = "en", limit = 12 } = {},
) {
  const book = new Set((bookIds || []).map(String));
  const symbol = String(ticker || "").trim().toLowerCase();
  const label = String(name || "").trim().toLowerCase();
  const now = Date.now();
  const scored = (rows || []).map((row) => {
    let score = 0;
    const title = String(row?.title || "");
    const titleZh = String(row?.title_zh || row?.headline_zh || row?.raw?.headline_zh || "");
    const displayTitle =
      lang === "zh" && titleZh.trim() ? titleZh.trim() : title;
    const hay = `${displayTitle} ${row?.summary || ""}`.toLowerCase();
    if ((row.companyIds || []).some((id) => book.has(String(id)))) score += 40;
    if (symbol && hay.includes(symbol)) score += 30;
    if (label && label.length > 3 && hay.includes(label)) score += 18;
    const cat = row.category || inferNewsCategory(row);
    if (cat === "filings") score += 22;
    if (cat === "research") score += 8;
    const source = String(row.source || "").toLowerCase();
    if (/reuters|bloomberg|wsj|ft|sec\.gov|edgar/.test(source)) score += 10;
    const stamp = Date.parse(row.ts || row.captured_at || "");
    if (Number.isFinite(stamp)) {
      const hours = Math.max(0, (now - stamp) / 3600000);
      score += Math.max(0, 24 - hours);
    }
    return { ...row, title: displayTitle, category: cat, _score: score };
  });
  scored.sort((a, b) => b._score - a._score || String(b.ts || "").localeCompare(String(a.ts || "")));
  return collapseDuplicateNews(scored).slice(0, limit);
}

function parseFinNumber(raw) {
  if (raw == null || raw === "" || raw === "—") return null;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  const text = String(raw).trim().replace(/[,$%\s]/g, "");
  if (!text || text === "-" || text === "—") return null;
  const mult =
    /t$/i.test(text) ? 1e12 : /b$/i.test(text) ? 1e9 : /m$/i.test(text) ? 1e6 : /k$/i.test(text) ? 1e3 : 1;
  const n = Number(text.replace(/[tbmK]$/i, ""));
  return Number.isFinite(n) ? n * mult : null;
}

const FA_LINE_PATTERNS = [
  { id: "revenue", re: /^(total\s+)?revenue|net\s+sales|sales$/i },
  { id: "gross_margin", re: /gross\s+margin/i },
  { id: "operating_income", re: /operating\s+income|income\s+from\s+operations/i },
  { id: "op_margin", re: /operating\s+margin/i },
  { id: "eps", re: /diluted\s+eps|earnings\s+per\s+share|eps$/i },
  { id: "fcf", re: /free\s+cash\s+flow|fcf/i },
  { id: "net_cash", re: /cash\s+and\s+cash\s+equivalents|net\s+cash/i },
];

/** Compact FA lite lines with YoY delta from Nasdaq-style tables. */
export function faLiteLines(financials = {}) {
  const income = financials?.income || {};
  const cashflow = financials?.cashflow || {};
  const ratios = financials?.ratios || {};
  const balance = financials?.balance || {};
  const tables = [income, ratios, cashflow, balance];
  const lines = [];
  for (const def of FA_LINE_PATTERNS) {
    let found = null;
    for (const table of tables) {
      for (const row of table?.rows || []) {
        if (!def.re.test(String(row.label || "").trim())) continue;
        found = row;
        break;
      }
      if (found) break;
    }
    if (!found) continue;
    const values = (found.values || []).map(parseFinNumber);
    const latest = values.find((n) => n != null);
    const prior = values.filter((n) => n != null)[1];
    let yoy = null;
    if (latest != null && prior != null && prior !== 0) {
      yoy = ((latest - prior) / Math.abs(prior)) * 100;
    }
    lines.push({
      id: def.id,
      label: found.label,
      latest,
      latestRaw: (found.values || [])[0] || "—",
      prior,
      yoy,
    });
  }
  return lines;
}

/** Ownership summary: top buyers/sellers from period change column. */
export function ownershipSummary(holders = {}) {
  const rows = (holders?.holders || []).map((row) => {
    const changeRaw = String(row.change_pct ?? row.change ?? "").trim();
    const change = parseFinNumber(changeRaw.replace(/%/g, ""));
    return {
      owner: row.owner || row.name || "—",
      shares: row.shares,
      value: row.value,
      change_pct: changeRaw || "—",
      change,
    };
  });
  const withChange = rows.filter((row) => Number.isFinite(row.change));
  const buyers = [...withChange].sort((a, b) => b.change - a.change).slice(0, 3);
  const sellers = [...withChange].sort((a, b) => a.change - b.change).slice(0, 3);
  return {
    ownership_pct: holders.ownership_pct || null,
    shares_out: holders.shares_out || null,
    holdings_value: holders.holdings_value || null,
    buyers,
    sellers,
    rows: rows.slice(0, 12),
  };
}

/** Filing / transcript snips from ranked desk rows (category filings). */
export function filingSnips(rows = [], { ticker = "", name = "", limit = 5 } = {}) {
  const ranked = rankDeskNews(rows, { ticker, name, limit: 40 });
  return ranked
    .filter((row) => (row.category || inferNewsCategory(row)) === "filings")
    .slice(0, limit);
}
