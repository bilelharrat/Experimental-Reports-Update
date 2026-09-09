/** Bloomberg-style Market command parser (NVDA, NEWS NVDA, COMP, TRACK…). */

const TICKER_RE = /^[A-Z][A-Z0-9.-]{0,9}$/;

const VERB_ACTIONS = {
  DES: "quote",
  Q: "quote",
  QUOTE: "quote",
  NEWS: "news",
  N: "news",
  HL: "news",
  CN: "news",
  COMP: "comp",
  PEER: "comp",
  PEERS: "comp",
  RV: "comp",
  REL: "comp",
  CAL: "calendar",
  EVTS: "calendar",
  EVENTS: "calendar",
  EARN: "calendar",
  TRACK: "tracking",
  WL: "tracking",
  WATCH: "tracking",
  HOME: "home",
  H: "home",
  PULSE: "pulse",
  MP: "pulse",
  HP: "hp",
  G: "hp",
  GRAPH: "hp",
  FA: "fa",
  FIN: "fa",
  EQS: "screener",
  SCR: "screener",
  SCREEN: "screener",
  WEI: "wei",
  MACRO: "wei",
  OWN: "owners",
  HOLD: "owners",
  ALERT: "alerts",
  ALERTS: "alerts",
  HEAT: "heatmap",
  HEATMAP: "heatmap",
  RRG: "rrg",
  ROT: "rrg",
  DESK: "desk",
  WORK: "desk",
  SESSION: "session",
  SES: "session",
  FILING: "filings",
  FILINGS: "filings",
  EDGAR: "filings",
  LOTS: "lots",
  TWO: "two",
  DES2: "two",
  ICS: "ics",
  NOTE: "notes",
  NOTES: "notes",
  ND: "newsdesk",
  NEWSDESK: "newsdesk",
  SIG: "signals",
  SIGNALS: "signals",
  BRIEF: "brief",
  MB: "brief",
  STATS: "stats",
  SR: "stockresearch",
  LIB: "library",
  SET: "settings",
  SETTINGS: "settings",
  HORMUZ: "hormuz",
  LAB: "lab",
};

// Verbs that just open an app view — no ticker argument.
const NAV_ACTIONS = new Set([
  "newsdesk",
  "signals",
  "brief",
  "stats",
  "stockresearch",
  "library",
  "settings",
  "hormuz",
  "lab",
]);

function normalizeToken(token) {
  return String(token || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9.-]/g, "");
}

export function parseMarketCommand(raw) {
  const text = String(raw || "").trim();
  if (!text) return null;
  const parts = text.split(/\s+/).filter(Boolean).map(normalizeToken).filter(Boolean);
  if (!parts.length) return null;

  const first = parts[0];
  const second = parts[1] || "";
  const action = VERB_ACTIONS[first];

  if (
    action === "home" ||
    action === "pulse" ||
    action === "wei" ||
    action === "alerts" ||
    action === "heatmap" ||
    action === "rrg" ||
    action === "session" ||
    action === "ics" ||
    NAV_ACTIONS.has(action)
  ) {
    return { action, ticker: null, label: first.toLowerCase(), raw: text };
  }
  if (action === "two" || action === "notes") {
    const ticker = second && TICKER_RE.test(second) && !VERB_ACTIONS[second] ? second : null;
    return { action, ticker, label: first.toLowerCase(), raw: text };
  }
  if (action === "desk") {
    return {
      action,
      ticker: null,
      desk: second && !TICKER_RE.test(second) ? second : second || null,
      label: "desk",
      raw: text,
    };
  }
  if (action === "lots") {
    return { action: "lots", ticker: null, label: "lots", raw: text };
  }
  if (action === "calendar" || action === "screener") {
    const ticker = second && TICKER_RE.test(second) && !VERB_ACTIONS[second] ? second : null;
    return {
      action,
      ticker,
      screen: action === "screener" && second && !ticker ? second : null,
      label: first.toLowerCase(),
      raw: text,
    };
  }
  if (action === "tracking") {
    const ticker = second && TICKER_RE.test(second) && !VERB_ACTIONS[second] ? second : null;
    return { action, ticker, label: "track", raw: text };
  }
  if (
    action === "news" ||
    action === "comp" ||
    action === "quote" ||
    action === "hp" ||
    action === "fa" ||
    action === "owners" ||
    action === "filings"
  ) {
    const ticker = second && TICKER_RE.test(second) && !VERB_ACTIONS[second] ? second : null;
    if (
      !ticker &&
      action !== "quote" &&
      action !== "hp" &&
      action !== "fa" &&
      action !== "owners" &&
      action !== "filings"
    ) {
      return { action, ticker: null, label: first.toLowerCase(), raw: text };
    }
    if (ticker) return { action, ticker, label: first.toLowerCase(), raw: text };
    if (action === "hp" || action === "fa" || action === "owners" || action === "filings") {
      return { action, ticker: null, label: first.toLowerCase(), raw: text };
    }
  }

  if (TICKER_RE.test(first) && !VERB_ACTIONS[first] && parts.length === 1) {
    return { action: "quote", ticker: first, label: "des", raw: text };
  }

  return { action: "search", ticker: null, query: text, label: "search", raw: text };
}

export function suggestMarketCommands(raw, { companies = [], limit = 8 } = {}) {
  const text = String(raw || "").trim();
  const parsed = parseMarketCommand(text);
  const suggestions = [];
  const push = (row) => {
    if (suggestions.length >= limit) return;
    if (suggestions.some((item) => item.id === row.id)) return;
    suggestions.push(row);
  };

  if (parsed?.action === "quote" && parsed.ticker) {
    push({
      id: `quote:${parsed.ticker}`,
      title: parsed.ticker,
      subtitle: "DES · Market quote",
      action: "quote",
      ticker: parsed.ticker,
    });
    push({
      id: `news:${parsed.ticker}`,
      title: `NEWS ${parsed.ticker}`,
      subtitle: "Headlines for this symbol",
      action: "news",
      ticker: parsed.ticker,
    });
    push({
      id: `comp:${parsed.ticker}`,
      title: `PEER ${parsed.ticker}`,
      subtitle: "COMP / RV peers",
      action: "comp",
      ticker: parsed.ticker,
    });
    push({
      id: `hp:${parsed.ticker}`,
      title: `HP ${parsed.ticker}`,
      subtitle: "History / compare graph",
      action: "hp",
      ticker: parsed.ticker,
    });
  } else if (parsed && parsed.action !== "search") {
    push({
      id: `${parsed.action}:${parsed.ticker || parsed.screen || ""}`,
      title: String(parsed.raw || "").toUpperCase(),
      subtitle: commandSubtitle(parsed),
      action: parsed.action,
      ticker: parsed.ticker,
      companyId: parsed.companyId,
      query: parsed.query,
      screen: parsed.screen,
    });
  }

  const q = text.toLowerCase();
  if (q) {
    for (const company of companies) {
      const ticker = String(company?.ticker || "").trim().toUpperCase();
      const name = String(company?.name || "");
      const hay = `${ticker} ${name}`.toLowerCase();
      if (!hay.includes(q) && !(ticker && ticker.startsWith(text.toUpperCase()))) continue;
      push({
        id: `company:${company.id}`,
        title: ticker || name,
        subtitle: name,
        action: ticker ? "quote" : "company",
        ticker: ticker || null,
        companyId: company.id,
      });
    }
  }

  if (!suggestions.length) {
    push({
      id: "help",
      title: "NVDA · HP · FA · HEAT · RRG · DESK · EVTS",
      subtitle: "Command examples",
      action: "help",
    });
  }
  return suggestions.slice(0, limit);
}

function commandSubtitle(parsed) {
  if (parsed.action === "news") return "Open Market headlines";
  if (parsed.action === "comp") return "Open COMP / RV peers";
  if (parsed.action === "calendar") return "Watchlist event calendar";
  if (parsed.action === "tracking") return "Open Tracking";
  if (parsed.action === "home") return "Home desk";
  if (parsed.action === "pulse") return "Pulse";
  if (parsed.action === "quote") return "Market quote";
  if (parsed.action === "hp") return "HP history workbench";
  if (parsed.action === "fa") return "FA lite financials";
  if (parsed.action === "screener") return "EQS screener";
  if (parsed.action === "wei") return "WEI macro strip";
  if (parsed.action === "owners") return "Ownership summary";
  if (parsed.action === "alerts") return "Alert rules";
  if (parsed.action === "heatmap") return "Sector heat map";
  if (parsed.action === "rrg") return "RRG-lite rotation";
  if (parsed.action === "desk") return "Saved Market desk";
  if (parsed.action === "session") return "1D session + VWAP";
  if (parsed.action === "filings") return "EDGAR filings";
  if (parsed.action === "lots") return "Book lots";
  if (parsed.action === "two") return "2-up DES quotes";
  if (parsed.action === "ics") return "Export EVTS calendar";
  if (parsed.action === "notes") return "Ticker notes";
  if (parsed.action === "newsdesk") return "News desk";
  if (parsed.action === "signals") return "Signals lab";
  if (parsed.action === "brief") return "Morning Brief on Pulse";
  if (parsed.action === "stats") return "Trader stats";
  if (parsed.action === "stockresearch") return "Stock research trackers";
  if (parsed.action === "library") return "Source library";
  if (parsed.action === "settings") return "Settings";
  if (parsed.action === "hormuz") return "Hormuz library";
  if (parsed.action === "lab") return "Innovation lab";
  return "Run command";
}

export function routeForMarketCommand(cmd) {
  if (!cmd) return null;
  if (cmd.action === "home") return { name: "home" };
  if (cmd.action === "tracking") return { name: "tracking" };
  if (cmd.action === "pulse") return { name: "weekly-summary" };
  if (cmd.action === "company" && cmd.companyId) {
    return { name: "research", params: { companyId: cmd.companyId } };
  }
  if (cmd.action === "calendar") {
    return {
      name: "market-radar",
      query: {
        ...(cmd.ticker ? { ticker: cmd.ticker } : {}),
        panel: "calendar",
      },
    };
  }
  if (cmd.action === "news") {
    return {
      name: "market-radar",
      query: {
        ...(cmd.ticker ? { ticker: cmd.ticker } : {}),
        panel: "news",
      },
    };
  }
  if (cmd.action === "comp") {
    return {
      name: "market-radar",
      query: {
        ...(cmd.ticker ? { ticker: cmd.ticker } : {}),
        panel: "peers",
      },
    };
  }
  if (cmd.action === "hp") {
    return {
      name: "market-radar",
      query: {
        ...(cmd.ticker ? { ticker: cmd.ticker } : {}),
        panel: "hp",
      },
    };
  }
  if (cmd.action === "fa") {
    return {
      name: "market-radar",
      query: {
        ...(cmd.ticker ? { ticker: cmd.ticker } : {}),
        panel: "fa",
        tab: "financials",
      },
    };
  }
  if (cmd.action === "screener") {
    return {
      name: "market-radar",
      query: {
        panel: "screener",
        ...(cmd.screen ? { screen: cmd.screen } : {}),
      },
    };
  }
  if (cmd.action === "wei") {
    return { name: "market-radar", query: { panel: "wei" } };
  }
  if (cmd.action === "owners") {
    return {
      name: "market-radar",
      query: {
        ...(cmd.ticker ? { ticker: cmd.ticker } : {}),
        panel: "owners",
        tab: "holders",
      },
    };
  }
  if (cmd.action === "alerts") {
    return { name: "market-radar", query: { panel: "alerts" } };
  }
  if (cmd.action === "heatmap") {
    return { name: "market-radar", query: { panel: "heatmap" } };
  }
  if (cmd.action === "rrg") {
    return {
      name: "market-radar",
      query: { ...(cmd.ticker ? { ticker: cmd.ticker } : {}), panel: "rrg" },
    };
  }
  if (cmd.action === "session") {
    return {
      name: "market-radar",
      query: { ...(cmd.ticker ? { ticker: cmd.ticker } : {}), panel: "hp", range: "1d" },
    };
  }
  if (cmd.action === "filings") {
    return {
      name: "market-radar",
      query: { ...(cmd.ticker ? { ticker: cmd.ticker } : {}), panel: "filings" },
    };
  }
  if (cmd.action === "desk") {
    return {
      name: "market-radar",
      query: { ...(cmd.desk ? { desk: cmd.desk } : {}), panel: "desk" },
    };
  }
  if (cmd.action === "lots") {
    return { name: "tracking", query: { panel: "lots" } };
  }
  if (cmd.action === "two") {
    return {
      name: "market-radar",
      query: { ...(cmd.ticker ? { ticker: cmd.ticker } : {}), two: "1" },
    };
  }
  if (cmd.action === "ics") {
    return { name: "market-radar", query: { panel: "calendar", ics: "1" } };
  }
  if (cmd.action === "notes") {
    return {
      name: "market-radar",
      query: { ...(cmd.ticker ? { ticker: cmd.ticker } : {}), panel: "notes" },
    };
  }
  if (cmd.action === "quote" && cmd.ticker) {
    return { name: "market-radar", query: { ticker: cmd.ticker } };
  }
  if (cmd.action === "newsdesk") return { name: "news-desk" };
  if (cmd.action === "signals") return { name: "research-page-market-pulse" };
  if (cmd.action === "brief") {
    return { name: "weekly-summary", query: { panel: "brief" } };
  }
  if (cmd.action === "stats") return { name: "trader-stats" };
  if (cmd.action === "stockresearch") return { name: "stock-research" };
  if (cmd.action === "library") return { name: "source-library" };
  if (cmd.action === "settings") return { name: "settings" };
  if (cmd.action === "hormuz") return { name: "hormuz-library" };
  if (cmd.action === "lab") return { name: "innovation-lab" };
  if (cmd.action === "search" && cmd.query) {
    return { name: "home", query: { q: cmd.query } };
  }
  return null;
}
