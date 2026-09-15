export function isPublicCompany(company) {
  const type = String(company?.company_type || "").toLowerCase();
  const status = String(company?.status || "").toLowerCase();
  return (
    type === "public" ||
    status === "public" ||
    Boolean(String(company?.ticker || "").trim())
  );
}

function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[,.]/g, "")
    .replace(/\s+/g, " ");
}

export function displayTicker(company, companies = []) {
  const own = String(company?.ticker || "").trim();
  if (own) return own.toUpperCase();
  const parentKey = normalizeKey(company?.parent_company);
  if (!parentKey) return "";
  const parent = companies.find((row) => {
    if (!row || String(row.id) === String(company?.id)) return false;
    const name = normalizeKey(row.name);
    const id = normalizeKey(row.id);
    return Boolean((name && name === parentKey) || (id && id === parentKey));
  });
  return String(parent?.ticker || "").trim().toUpperCase();
}

export function publicTickers(companies = []) {
  const seen = new Set();
  const tickers = [];
  for (const company of companies) {
    if (!isPublicCompany(company)) continue;
    const ticker = String(company.ticker || "").trim().toUpperCase();
    if (!ticker || seen.has(ticker)) continue;
    seen.add(ticker);
    tickers.push(ticker);
  }
  return tickers;
}

export function lastPriceLabel(price) {
  if (price?.last == null || Number.isNaN(Number(price.last))) return null;
  const symbol = !price.currency || price.currency === "USD" ? "$" : `${price.currency} `;
  return `${symbol}${Number(price.last).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  })}`;
}

export function signedChange(value) {
  if (value == null || Number.isNaN(Number(value))) return null;
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

/**
 * Data-health read on a quote's `as_of` stamp.
 *
 * `stale` flips once the print is older than `staleMinutes` (default 20 —
 * enough to ride out provider hiccups without flagging every weekend
 * quote during RTH-adjacent use). Returns null when there is no stamp,
 * so callers can distinguish "no data" from "old data".
 */
export function quoteStaleness(asOf, { now = Date.now(), staleMinutes = 20 } = {}) {
  const stamp = Date.parse(String(asOf || ""));
  if (!Number.isFinite(stamp)) return null;
  const ageMinutes = Math.max(0, Math.round((now - stamp) / 60000));
  return { ageMinutes, stale: ageMinutes >= staleMinutes };
}

/** Broad-market ETFs the Home tape falls back to when nothing else is live. */
export const TAPE_BENCHMARK_TICKERS = ["SPY", "QQQ", "DIA", "IWM", "GLD", "TLT"];

/**
 * Tickers for the Home tape: the workspace's public companies when it has
 * any; otherwise the Market watchlist pins followed by broad-market
 * benchmarks, so a book of private companies (or a stray pin) still gets a
 * useful live tape.
 */
export function homeTapeTickers(companies = [], pinned = []) {
  const fromCompanies = publicTickers(companies);
  if (fromCompanies.length) return fromCompanies;
  const pins = (pinned || [])
    .map((ticker) => String(ticker || "").trim().toUpperCase())
    .filter(Boolean);
  return [...new Set([...pins, ...TAPE_BENCHMARK_TICKERS])];
}

export function buildTickerTape(companies = [], quotes = {}, tickers = publicTickers(companies)) {
  return tickers.map((ticker) => {
    const company = companies.find(
      (row) => String(row.ticker || "").trim().toUpperCase() === ticker,
    );
    const quote = quotes[ticker] || null;
    const day = quote?.change_pct_1d;
    return {
      ticker,
      name: company?.name || ticker,
      companyId: company?.id,
      quote,
      lastPrice: lastPriceLabel(
        quote?.last_price != null
          ? { last: Number(quote.last_price), currency: quote.currency || "USD" }
          : null,
      ),
      day: day != null ? Number(day) : null,
      up: day != null && Number(day) >= 0,
    };
  });
}
