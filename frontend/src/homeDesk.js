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
    item?.source,
    item?.domain,
    item?.category,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
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
  const hay = newsHaystack(item);
  for (const company of companies) {
    const name = String(company?.name || "").trim().toLowerCase();
    const ticker = String(company?.ticker || "").trim().toLowerCase();
    if (name && name.length >= 3 && hay.includes(name)) push(company);
    if (ticker && hay.includes(ticker)) push(company);
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
  return {
    id: String(extras.id || item.id || ""),
    title: newsTitle(item),
    summary: String(item.summary || item.description || "").trim(),
    source: String(item.source || item.domain || item.kind || "").trim(),
    url: String(item.source_url || item.url || "").trim(),
    ts: newsTimestamp(item),
    category,
    kind: extras.kind || item.kind || "news",
    market: Boolean(extras.market ?? isMarketNews(item, matched)),
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
    },
    [company],
    {
      id,
      matched: [company],
      kind: "company_news",
      market: false,
    },
  );
}

export function assembleDeskNews({ feed = [], companies = [] } = {}) {
  const rows = [];
  const seen = new Set();
  const push = (row) => {
    if (!row?.id || seen.has(row.id)) return;
    const key = `${row.url || ""}|${row.title}|${row.companyIds[0] || ""}`;
    if (seen.has(key)) return;
    seen.add(row.id);
    seen.add(key);
    rows.push(row);
  };
  for (const item of feed) {
    push(normalizeFeedItem(item, companies));
  }
  for (const company of companies) {
    const local = Array.isArray(company.company_news) && company.company_news.length
      ? company.company_news
      : company.recent_news || [];
    local.forEach((item, index) => {
      push(normalizeCompanyNews(company, item, index));
    });
  }
  rows.sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
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
