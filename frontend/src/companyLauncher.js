/**
 * The company launcher: clicking a company in the sidebar fills the content
 * area with a chooser — its reports, its news, or the Research Desk — each
 * previewed from data the app already holds. The view is
 * components/CompanyLauncher.vue; these helpers are the testable parts.
 */
import { ref, unref, watch } from "vue";
import { api } from "./api.js";
import { assembleDeskNews } from "./homeDesk.js";
import { formatCompactNumber } from "./formatters.js";

export { normalizeReportStatus } from "./formatters.js";

/** The company's reports, newest first — the rows its Reports page lists. */
export function companyReports(reports = [], companyId = "") {
  const id = String(companyId || "");
  if (!id) return [];
  return (reports || [])
    .filter((report) => report && String(report.company_id || "") === id)
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
}

/** The server's own label ("Buffett Investment Memo") before the raw kind. */
export function reportTitle(report) {
  const named = String(report?.title || report?.report_type || "").trim();
  if (named) return named;
  return String(report?.kind || "")
    .replace(/_/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function reportLanguages(report) {
  return Object.keys(report?.download_urls || {}).map((key) => key.toUpperCase());
}

/** The company's headlines, built exactly as the News desk builds them. */
export function companyHeadlines({ feed = [], companies = [], live = [], companyId = "", limit = 30, now } = {}) {
  if (!companyId) return [];
  return assembleDeskNews({ feed, companies, live, focusCompanyId: companyId, limit, now });
}

/**
 * Live headlines for one ticker. The app polls the wire for the first ten
 * tickers only, so a company further down the list would show no news at
 * all; asking for its own ticker fills that in. A plain quotes call — no AI.
 */
export function useTickerNews(tickerSource, { limit = 30 } = {}) {
  const items = ref([]);
  let request = 0;
  watch(
    () => String(unref(tickerSource) || "").trim().toUpperCase(),
    async (ticker) => {
      const id = ++request;
      items.value = [];
      if (!ticker) return;
      try {
        const payload = await api.quotesNews({ tickers: [ticker], limit });
        if (id === request) items.value = Array.isArray(payload?.items) ? payload.items : [];
      } catch {
        // The desk's own tape still shows; this only adds to it.
      }
    },
    { immediate: true },
  );
  return items;
}

/** A company field in the reader's language, as the Research view picks it. */
export function translatedField(company, field, lang = "en") {
  const c = company || {};
  const sourceIsZh = c.language === "zh";
  const needsTranslation =
    c.translation && ((lang === "zh" && !sourceIsZh) || (lang === "en" && sourceIsZh));
  if (needsTranslation && c.translation?.[field]) return c.translation[field];
  return c[field];
}

export function formatPrice(value, currency = "USD") {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return `$${n.toFixed(2)}`;
  }
}

// "$100,000,000+" → "$100M+". Anything that isn't a plain amount stays as
// written: "Series B" or "~$45B" already reads well.
export function compactMoney(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  const match = raw.match(/^([~≈]?)\$?\s*([\d,]+(?:\.\d+)?)\s*(\+?)$/);
  if (!match) return raw;
  const amount = Number(match[2].replace(/,/g, ""));
  if (!Number.isFinite(amount)) return raw;
  return `${match[1]}${formatCompactNumber(amount, { currency: true })}${match[3]}`;
}

/**
 * Facts for the Research Desk card, up to eight: a listed company's
 * valuation first, then what the record knows (tracked metrics, money raised,
 * founding, home, headcount), then market detail to fill what room is left.
 * `key` names the label (see CompanyLauncher.vue); a metric carries its own
 * label from the record.
 */
export function companyFacts(company = {}, quote = null, { limit = 8 } = {}) {
  const facts = [];
  const push = (key, value, label = "") => {
    const text = String(value ?? "").trim();
    if (text && text !== "—") facts.push({ key, value: text, label });
  };
  const currency = quote?.currency || "USD";
  const range = (low, high) =>
    Number(low) > 0 && Number(high) > 0
      ? `${formatPrice(low, currency)} – ${formatPrice(high, currency)}`
      : "";
  if (quote) {
    if (Number(quote.market_cap) > 0) {
      push("market_cap", formatCompactNumber(quote.market_cap, { currency: currency === "USD" }));
    }
    // A loss-maker's P/E is noise; its EPS, further down, says it plainly.
    if (Number(quote.pe_ratio) > 0) push("pe", Number(quote.pe_ratio).toFixed(1));
    push("range", range(quote.fifty_two_week_low, quote.fifty_two_week_high));
    if (Number(quote.dividend_yield) > 0) {
      push("dividend", `${(Number(quote.dividend_yield) * 100).toFixed(2)}%`);
    }
  }
  const metrics = (company?.metrics || []).filter((m) => m?.label && m?.value).slice(0, 3);
  for (const metric of metrics) push("metric", metric.value, String(metric.label).trim());
  push("funding", compactMoney(company?.total_funding_usd));
  push("founded", company?.founded_year);
  push("hq", company?.hq);
  push("employees", company?.employee_band);
  push("round", company?.latest_funding?.round);
  if (quote) {
    const eps = quote.eps == null ? NaN : Number(quote.eps);
    if (Number.isFinite(eps) && eps !== 0) push("eps", formatPrice(eps, currency));
    if (Number(quote.volume) > 0) push("volume", formatCompactNumber(quote.volume));
    push("day_range", range(quote.low, quote.high));
    const beta = quote.beta == null ? NaN : Number(quote.beta);
    if (Number.isFinite(beta)) push("beta", beta.toFixed(2));
  }
  return facts.slice(0, limit);
}

/** What the desk already holds on the company, for the card's "On file". */
export function deskCoverage(company = {}) {
  const count = (list) => (Array.isArray(list) ? list.length : 0);
  const people = Math.max(count(company?.team_profiles), count(company?.key_people));
  return [
    { key: "products", count: count(company?.products) },
    { key: "competitors", count: count(company?.competitors) },
    { key: "people", count: people },
    { key: "contracts", count: count(company?.notable_contracts) },
    { key: "investors", count: count(company?.board_investors) },
  ].filter((row) => row.count > 0);
}

/** Named people on the record, leadership first, without repeats. */
export function companyPeople(company = {}, limit = 3) {
  const out = [];
  const seen = new Set();
  for (const person of [...(company?.key_people || []), ...(company?.team_profiles || [])]) {
    const name = String(person?.name || "").trim();
    const key = name.toLowerCase();
    if (!name || seen.has(key)) continue;
    seen.add(key);
    out.push({ name, role: String(person?.role || person?.title || "").trim() });
    if (out.length >= limit) break;
  }
  return out;
}

/** Closing prices for the header sparkline, oldest first. */
export function closingPrices(points = []) {
  return (points || []).map((point) => Number(point?.close)).filter(Number.isFinite);
}

/** Change across a price series, in percent. */
export function seriesChangePct(values = []) {
  if (values.length < 2 || !values[0]) return null;
  return ((values[values.length - 1] - values[0]) / values[0]) * 100;
}

/**
 * SVG paths for the header's price trace: the line and the closed area
 * beneath it, which carries the gradient wash.
 */
export function sparkAreaPaths(values = [], { width = 240, height = 64, pad = 3 } = {}) {
  const nums = (values || []).map(Number).filter(Number.isFinite);
  if (nums.length < 2) return { line: "", area: "" };
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const coords = nums.map((value, index) => [
    pad + (index / (nums.length - 1)) * innerW,
    pad + (1 - (value - min) / span) * innerH,
  ]);
  const line = coords
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");
  const first = coords[0];
  const last = coords[coords.length - 1];
  const area = `${line} L${last[0].toFixed(1)} ${height} L${first[0].toFixed(1)} ${height} Z`;
  return { line, area };
}
