/**
 * Zero-cost company logo resolver and URL generators.
 *
 * Uses Google's global edge favicon CDN and public vector mirrors.
 * $0.00 cost, 0 LLM tokens, no API keys, and cached directly by the browser.
 */

const TICKER_DOMAIN_MAP = {
  AAPL: "apple.com",
  NVDA: "nvidia.com",
  MSFT: "microsoft.com",
  GOOG: "google.com",
  GOOGL: "google.com",
  AMZN: "amazon.com",
  META: "meta.com",
  TSLA: "tesla.com",
  TSM: "tsmc.com",
  INTC: "intel.com",
  AMD: "amd.com",
  AMGN: "amgen.com",
  HIPO: "hippo.com",
  NB: "niocorp.com",
  JOYY: "joyy.com",
  HIND: "vyome.com",
  BABA: "alibaba.com",
  AVGO: "broadcom.com",
  ASML: "asml.com",
  QCOM: "qualcomm.com",
  ORCL: "oracle.com",
  CRM: "salesforce.com",
  NFLX: "netflix.com",
  UBER: "uber.com",
  PLTR: "palantir.com",
  COIN: "coinbase.com",
  HOOD: "robinhood.com",
  SNOW: "snowflake.com",
  CRWD: "crowdstrike.com",
  NET: "cloudflare.com",
  ARM: "arm.com",
  DELL: "dell.com",
  IBM: "ibm.com",
  CSCO: "cisco.com",
  ADBE: "adobe.com",
  NOW: "servicenow.com",
  INTU: "intuit.com",
  PYPL: "paypal.com",
  SQ: "block.xyz",
  SHOP: "shopify.com",
  SPOT: "spotify.com",
  ABNB: "airbnb.com",
  DASH: "doordash.com",
  RBLX: "roblox.com",
  SNAP: "snapchat.com",
  PINS: "pinterest.com",
  RDDT: "reddit.com",
  NN: "nextnav.com",
  KO: "coca-cola.com",
  OXY: "oxy.com",
  ATE: "alten.com",
  DIS: "disney.com",
  NKE: "nike.com",
  SBUX: "starbucks.com",
  MCD: "mcdonalds.com",
  WMT: "walmart.com",
  COST: "costco.com",
  JNJ: "jnj.com",
  PFE: "pfizer.com",
  UNH: "uhc.com",
  V: "visa.com",
  MA: "mastercard.com",
  JPM: "jpmorganchase.com",
  BAC: "bankofamerica.com",
  GS: "goldmansachs.com",
  MS: "morganstanley.com",
  XOM: "exxonmobil.com",
  CVX: "chevron.com",
};

const SLUG_DOMAIN_MAP = {
  anthropic: "anthropic.com",
  "anthropic-pbc": "anthropic.com",
  openai: "openai.com",
  "google-llc": "google.com",
  google: "google.com",
  "coca-cola": "coca-cola.com",
  "coca-cola-co": "coca-cola.com",
  ko: "coca-cola.com",
  oxy: "oxy.com",
  "occidental-petroleum": "oxy.com",
  "cienet-technologies-beijing-co-ltd": "cienet.com",
  "cienet-technologies": "cienet.com",
  cienet: "cienet.com",
  "clenet-technologies": "cienet.com",
  clenet: "cienet.com",
  "ceinet-data-co-ltd-中经网数据有限公司": "cei.cn",
  "中经网数据有限公司": "cei.cn",
  "ceinet-data": "cei.cn",
  ceinet: "cei.cn",
  "celnet-data": "cei.cn",
  celnet: "cei.cn",
  alten: "alten.com",
  ate: "alten.com",
  tsm: "tsmc.com",
  tsmc: "tsmc.com",
  zainar: "zainartech.com",
  "zainar-inc": "zainartech.com",
  zainartech: "zainartech.com",
  databricks: "databricks.com",
  stripe: "stripe.com",
  cerebras: "cerebras.ai",
  anduril: "anduril.com",
  spacex: "spacex.com",
  "scale-ai": "scale.com",
  scale: "scale.com",
  mistral: "mistral.ai",
  "mistral-ai": "mistral.ai",
  cohere: "cohere.com",
  perplexity: "perplexity.ai",
  xai: "x.ai",
  groq: "groq.com",
  figure: "figure.ai",
  "figure-ai": "figure.ai",
  coreweave: "coreweave.com",
  midjourney: "midjourney.com",
  huggingface: "huggingface.co",
  deepseek: "deepseek.com",
  "oasys-now": "oasysnow.com",
  oasysnow: "oasysnow.com",
  "oasis-security": "oasis.security",
  oasissecurity: "oasis.security",
};

/**
 * Clean a raw domain or website string to a bare domain name (e.g. "apple.com").
 */
export function normalizeDomain(raw) {
  if (!raw || typeof raw !== "string") return "";
  let d = raw.trim().toLowerCase();
  // Strip protocols
  d = d.replace(/^[a-z][a-z0-9+.-]*:\/\//i, "");
  // Strip path, query string, hash
  d = d.split("/")[0].split("?")[0].split("#")[0];
  // Strip auth and port
  d = d.replace(/^.*@/, "").split(":")[0];
  // Strip www prefix
  if (d.startsWith("www.")) {
    d = d.slice(4);
  }
  // Validate bare domain-like pattern (e.g. "foo.com" or "bar.co.uk")
  if (/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/.test(d)) {
    return d;
  }
  return "";
}

// Corporate words a name may end in without changing whose name it is:
// "Anthropic PBC" and "Databricks Inc." are still Anthropic and Databricks.
const NAME_SUFFIXES = new Set([
  "inc",
  "incorporated",
  "corp",
  "corporation",
  "co",
  "company",
  "ltd",
  "limited",
  "llc",
  "pbc",
  "plc",
  "sa",
  "ag",
  "gmbh",
  "holdings",
  "holding",
  "group",
  "technologies",
  "technology",
  "systems",
  "labs",
  "ai",
  "de",
]);

/**
 * A name reduced to the letters that identify it: lower case, punctuation
 * and trailing corporate words dropped ("Coca Cola Co" → "cocacola").
 * Latin letters only, so a Chinese name reduces to "" and never matches.
 */
function nameSlug(name) {
  const words = String(name || "")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
  while (words.length > 1 && NAME_SUFFIXES.has(words[words.length - 1])) words.pop();
  return words.join("");
}

/**
 * A key two spellings of one company's name share ("Microsoft" and
 * "Microsoft Corp"; "Anthropic, PBC" and "Anthropic"). A name with no Latin
 * letters (a Chinese name) is its own key, trimmed and lower-cased.
 */
export function companyNameKey(name) {
  return nameSlug(name) || String(name || "").trim().toLowerCase();
}

function nameIndex(map) {
  const index = new Map();
  for (const [key, value] of Object.entries(map)) {
    const slug = nameSlug(key);
    if (slug && !index.has(slug)) index.set(slug, value);
  }
  return index;
}

let slugDomainByName = null;
let highResByName = null;

// A name counts only when it IS a mapped name once its corporate suffix is
// dropped — never when it merely contains one. Substring matching gave
// "Anthropics Technology" Anthropic's mark, "Walten" ALTEN's and anything
// with "scale" in it Scale AI's.
function domainForName(name) {
  const slug = nameSlug(name);
  if (!slug) return "";
  if (!slugDomainByName) slugDomainByName = nameIndex(SLUG_DOMAIN_MAP);
  return slugDomainByName.get(slug) || "";
}

function highResLogoForName(name) {
  const slug = nameSlug(name);
  if (!slug) return "";
  if (!highResByName) highResByName = nameIndex(HIGH_RES_LOGOS);
  return highResByName.get(slug) || "";
}

// What a report snapshotted of its company when it was created
// (server/report_reader.py IDENTITY_FIELDS). It wins over the live record,
// which may have been edited — or re-pointed at another entity — since.
const SNAPSHOT_FIELDS = ["ticker", "website", "logo_domain", "logo_url", "legal_name"];

function logoIdentity(company) {
  const snapshot = company?.company_identity;
  if (!snapshot || typeof snapshot !== "object") return company;
  const merged = { ...company };
  for (const key of SNAPSHOT_FIELDS) {
    if (snapshot[key]) merged[key] = snapshot[key];
  }
  return merged;
}

/**
 * What tells a company from its lookalikes, for a line under its name: the
 * legal entity (when it reads differently from the display name), the
 * one-line disambiguator the company search wrote, and the company's own
 * domain. Empty when the record carries none of them.
 */
export function companyIdentityParts(company) {
  if (!company || typeof company !== "object") return [];
  const parts = [];
  const name = String(company.name || "").trim().toLowerCase();
  const legal = String(company.legal_name || "").trim();
  if (legal && legal.toLowerCase() !== name) parts.push(legal);
  const disambiguator = String(company.disambiguator || "").trim();
  if (disambiguator) parts.push(disambiguator);
  const domain = normalizeDomain(company.website) || normalizeDomain(company.logo_domain);
  if (domain) parts.push(domain);
  return parts;
}

/**
 * Deterministically resolve a bare domain for a company object or string without any LLM/API calls.
 * The record's own domain and ticker come first; the maps only fill in for
 * an exact id, or an exact name (see `domainForName`).
 */
export function resolveCompanyDomain(company) {
  if (!company) return "";
  if (typeof company === "string") {
    const fromStr = normalizeDomain(company);
    if (fromStr) return fromStr;
    const slug = company.trim().toLowerCase();
    if (SLUG_DOMAIN_MAP[slug]) return SLUG_DOMAIN_MAP[slug];
    const ticker = slug.toUpperCase();
    if (TICKER_DOMAIN_MAP[ticker]) return TICKER_DOMAIN_MAP[ticker];
    return "";
  }
  const identity = logoIdentity(company);

  // 1. Explicit logo_domain
  const fromLogoDomain = normalizeDomain(identity.logo_domain);
  if (fromLogoDomain) return fromLogoDomain;

  // 2. Explicit website
  const fromWebsite = normalizeDomain(identity.website);
  if (fromWebsite) return fromWebsite;

  // 3. Ticker mapping
  const ticker = String(identity.ticker || "").trim().toUpperCase();
  if (ticker && TICKER_DOMAIN_MAP[ticker]) {
    return TICKER_DOMAIN_MAP[ticker];
  }

  // 4. Company id mapping
  const id = String(identity.id || "").trim().toLowerCase();
  if (id) {
    if (SLUG_DOMAIN_MAP[id]) return SLUG_DOMAIN_MAP[id];
    const fromIdTicker = id.toUpperCase();
    if (TICKER_DOMAIN_MAP[fromIdTicker]) return TICKER_DOMAIN_MAP[fromIdTicker];
  }

  // 5. The name, when it is exactly a mapped name
  return domainForName(identity.name);
}

/**
 * Curated high-resolution vectors and 256px CDN marks for frontier AI labs and key private companies.
 * $0.00 cost, zero rate limits, cached at global CDN edges.
 */
export const HIGH_RES_LOGOS = {
  anthropic: "https://api.iconify.design/simple-icons:anthropic.svg?color=%23D97757",
  "anthropic-pbc": "https://api.iconify.design/simple-icons:anthropic.svg?color=%23D97757",
  openai: "https://api.iconify.design/simple-icons:openai.svg?color=%2310a37f",
  "google-llc": "https://assets.parqet.com/logos/symbol/GOOG",
  ko: "https://assets.parqet.com/logos/symbol/KO",
  oxy: "https://assets.parqet.com/logos/symbol/OXY",
  tsm: "https://assets.parqet.com/logos/symbol/TSM",
  "cienet-technologies-beijing-co-ltd": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
  "cienet-technologies": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
  cienet: "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
  "clenet-technologies": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
  clenet: "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
  "ceinet-data-co-ltd-中经网数据有限公司": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
  "中经网数据有限公司": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
  "ceinet-data": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
  ceinet: "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
  "celnet-data": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
  celnet: "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://www.cei.cn&size=128",
  ate: "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://alten.com&size=128",
  alten: "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://alten.com&size=128",
  "oasys-now": "https://framerusercontent.com/images/ctwK8JfDzLYECpwWHw7fd1rrZU.svg",
  oasysnow: "https://framerusercontent.com/images/ctwK8JfDzLYECpwWHw7fd1rrZU.svg",
  "oasis-security": "https://cdn.prod.website-files.com/652ba09e4e7b1ba97dd01e7b/65c1f63438246a4ad5bcbed5_O%20(4).png",
  oasissecurity: "https://cdn.prod.website-files.com/652ba09e4e7b1ba97dd01e7b/65c1f63438246a4ad5bcbed5_O%20(4).png",
  cerebras: "https://avatars.githubusercontent.com/Cerebras?s=256",
  databricks: "https://api.iconify.design/simple-icons:databricks.svg?color=%23FF3621",
  stripe: "https://api.iconify.design/simple-icons:stripe.svg?color=%23635BFF",
  mistral: "https://api.iconify.design/simple-icons:mistral.svg?color=%23F54E00",
  "mistral-ai": "https://api.iconify.design/simple-icons:mistral.svg?color=%23F54E00",
  perplexity: "https://api.iconify.design/simple-icons:perplexity.svg?color=%231B998B",
  spacex: "https://api.iconify.design/simple-icons:spacex.svg?color=%23000000",
  anduril: "https://avatars.githubusercontent.com/anduril?s=256",
  "scale-ai": "https://api.iconify.design/simple-icons:scale.svg?color=%23000000",
  scale: "https://api.iconify.design/simple-icons:scale.svg?color=%23000000",
  midjourney: "https://api.iconify.design/simple-icons:midjourney.svg?color=%23000000",
  huggingface: "https://api.iconify.design/simple-icons:huggingface.svg?color=%23FFD21E",
  deepseek: "https://avatars.githubusercontent.com/deepseek-ai?s=256",
  cohere: "https://avatars.githubusercontent.com/cohere-ai?s=256",
  figure: "https://avatars.githubusercontent.com/Figure-AI?s=256",
  "figure-ai": "https://avatars.githubusercontent.com/Figure-AI?s=256",
  groq: "https://avatars.githubusercontent.com/groq?s=256",
  coreweave: "https://avatars.githubusercontent.com/coreweave?s=256",
  xai: "https://api.iconify.design/simple-icons:x.svg?color=%23000000",
  "zainar-inc": "https://zainartech.com/favicon.ico?favicon.d517f128.ico",
  zainar: "https://zainartech.com/favicon.ico?favicon.d517f128.ico",
};

/**
 * Return vector SVG mark for public stock symbols from Parqet's public asset CDN.
 */
export function parqetLogoUrl(ticker) {
  if (!ticker || typeof ticker !== "string") return "";
  const t = ticker.trim().toUpperCase();
  return t ? `https://assets.parqet.com/logos/symbol/${encodeURIComponent(t)}` : "";
}

/**
 * Return Google's official public favicon URL (128px high-res edge CDN).
 * Completely free, globally edge-cached, zero rate limits.
 */
export function googleFaviconUrl(domain) {
  const d = normalizeDomain(domain);
  if (!d) return "";
  return `https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://${encodeURIComponent(d)}&size=128`;
}

/**
 * Return DuckDuckGo's public icon URL as secondary fallback.
 */
export function duckduckgoFaviconUrl(domain) {
  const d = normalizeDomain(domain);
  if (!d) return "";
  return `https://icons.duckduckgo.com/ip3/${encodeURIComponent(d)}.ico`;
}

/**
 * Return the primary company logo URL.
 *
 * Whose logo it is comes first: a report's identity snapshot, then the
 * record's own logo, ticker and domain (the same order as the server's
 * _company_logo_url). The curated marks and slug maps only fill in for an
 * exact id or an exact name — no name patterns, so a lookalike company never
 * wears a famous company's logo. Nothing found means initials.
 */
export function companyLogoUrl(company) {
  if (!company) return "";
  const identity = typeof company === "object" ? logoIdentity(company) : null;
  if (identity?.logo_url) {
    return identity.logo_url;
  }

  // 1. The record's own ticker: a vector SVG.
  const ownTicker = String(identity?.ticker || "").trim().toUpperCase();
  if (ownTicker) {
    return parqetLogoUrl(ownTicker);
  }

  // 2. The record's own domain.
  const ownDomain = identity
    ? normalizeDomain(identity.logo_domain) || normalizeDomain(identity.website)
    : "";
  if (ownDomain) {
    return googleFaviconUrl(ownDomain);
  }

  // 3. Curated vector / 256px high-res assets by exact id or exact name
  const id = String((identity ? identity.id : company) || "").trim().toLowerCase();
  if (id && HIGH_RES_LOGOS[id]) {
    return HIGH_RES_LOGOS[id];
  }
  const curatedByName = identity ? highResLogoForName(identity.name) : "";
  if (curatedByName) {
    return curatedByName;
  }

  // 4. An id that is itself a ticker ("ko", "oxy").
  if (id && id.length <= 5 && TICKER_DOMAIN_MAP[id.toUpperCase()]) {
    return parqetLogoUrl(id.toUpperCase());
  }

  // 5. Google 128px edge favicon CDN for a mapped domain
  const domain = resolveCompanyDomain(identity || company);
  if (!domain) return "";
  return googleFaviconUrl(domain);
}

/**
 * Return the secondary fallback logo URL.
 */
export function companyFallbackLogoUrl(company) {
  const identity = typeof company === "object" && company ? logoIdentity(company) : company;
  const domain = resolveCompanyDomain(identity);
  if (!domain) return "";
  const ticker = (typeof identity === "object" ? String(identity.ticker || "") : "").trim().toUpperCase();
  const id = String((typeof identity === "object" ? identity.id : identity) || "").trim().toLowerCase();
  // If primary was high-res Parqet SVG or curated mark, fallback to Google CDN
  if (ticker || HIGH_RES_LOGOS[id]) {
    return googleFaviconUrl(domain);
  }
  // Otherwise fallback to DuckDuckGo
  return duckduckgoFaviconUrl(domain);
}

