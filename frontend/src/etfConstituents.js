/** Static top ETF weight tables (public-data stand-in for fund holdings APIs). */

export const ETF_CONSTITUENTS = {
  SPY: {
    name: "S&P 500",
    asOf: "2026-Q1 illustrative",
    holdings: [
      { ticker: "NVDA", name: "NVIDIA", weight: 7.2 },
      { ticker: "MSFT", name: "Microsoft", weight: 6.8 },
      { ticker: "AAPL", name: "Apple", weight: 6.5 },
      { ticker: "AMZN", name: "Amazon", weight: 3.8 },
      { ticker: "META", name: "Meta", weight: 2.9 },
      { ticker: "GOOGL", name: "Alphabet A", weight: 2.1 },
      { ticker: "AVGO", name: "Broadcom", weight: 2.0 },
      { ticker: "GOOG", name: "Alphabet C", weight: 1.8 },
      { ticker: "BRK.B", name: "Berkshire B", weight: 1.7 },
      { ticker: "TSLA", name: "Tesla", weight: 1.6 },
    ],
  },
  QQQ: {
    name: "Nasdaq 100",
    asOf: "2026-Q1 illustrative",
    holdings: [
      { ticker: "NVDA", name: "NVIDIA", weight: 9.5 },
      { ticker: "MSFT", name: "Microsoft", weight: 8.4 },
      { ticker: "AAPL", name: "Apple", weight: 8.1 },
      { ticker: "AMZN", name: "Amazon", weight: 5.6 },
      { ticker: "META", name: "Meta", weight: 4.8 },
      { ticker: "AVGO", name: "Broadcom", weight: 4.2 },
      { ticker: "GOOGL", name: "Alphabet A", weight: 2.9 },
      { ticker: "GOOG", name: "Alphabet C", weight: 2.8 },
      { ticker: "TSLA", name: "Tesla", weight: 2.7 },
      { ticker: "COST", name: "Costco", weight: 2.4 },
    ],
  },
  DIA: {
    name: "Dow 30",
    asOf: "2026-Q1 illustrative",
    holdings: [
      { ticker: "GS", name: "Goldman Sachs", weight: 9.2 },
      { ticker: "MSFT", name: "Microsoft", weight: 7.1 },
      { ticker: "CAT", name: "Caterpillar", weight: 6.4 },
      { ticker: "HD", name: "Home Depot", weight: 6.1 },
      { ticker: "V", name: "Visa", weight: 5.5 },
      { ticker: "SHW", name: "Sherwin-Williams", weight: 5.2 },
      { ticker: "UNH", name: "UnitedHealth", weight: 4.8 },
      { ticker: "AXP", name: "American Express", weight: 4.5 },
      { ticker: "AMGN", name: "Amgen", weight: 4.3 },
      { ticker: "JPM", name: "JPMorgan", weight: 4.1 },
    ],
  },
  IWM: {
    name: "Russell 2000",
    asOf: "2026-Q1 illustrative",
    holdings: [
      { ticker: "SMCI", name: "Super Micro", weight: 0.7 },
      { ticker: "FTAI", name: "FTAI Aviation", weight: 0.5 },
      { ticker: "INSM", name: "Insmed", weight: 0.4 },
      { ticker: "SATS", name: "EchoStar", weight: 0.4 },
      { ticker: "FIX", name: "Comfort Systems", weight: 0.4 },
      { ticker: "FN", name: "Fabrinet", weight: 0.3 },
      { ticker: "CRS", name: "Carpenter Tech", weight: 0.3 },
      { ticker: "MLI", name: "Mueller Industries", weight: 0.3 },
      { ticker: "AIT", name: "Applied Industrial", weight: 0.3 },
      { ticker: "UFPI", name: "UFP Industries", weight: 0.3 },
    ],
  },
  TLT: {
    name: "20+ Year Treasury",
    asOf: "2026-Q1 illustrative",
    holdings: [
      { ticker: "US912810", name: "Treasury 2053+", weight: 4.2 },
      { ticker: "US912810B", name: "Treasury 2052", weight: 3.9 },
      { ticker: "US912810C", name: "Treasury 2051", weight: 3.7 },
      { ticker: "US912810D", name: "Treasury 2050", weight: 3.5 },
      { ticker: "US912810E", name: "Treasury 2049", weight: 3.4 },
      { ticker: "US912810F", name: "Treasury 2048", weight: 3.2 },
      { ticker: "US912810G", name: "Treasury 2047", weight: 3.1 },
      { ticker: "US912810H", name: "Treasury 2046", weight: 3.0 },
      { ticker: "US912810I", name: "Treasury 2045", weight: 2.9 },
      { ticker: "US912810J", name: "Treasury 2044", weight: 2.8 },
    ],
  },
};

export const KNOWN_ETF_TICKERS = Object.keys(ETF_CONSTITUENTS);

export function etfConstituents(ticker) {
  const symbol = String(ticker || "").trim().toUpperCase();
  return ETF_CONSTITUENTS[symbol] || null;
}

export function isKnownEtf(ticker) {
  return Boolean(etfConstituents(ticker));
}

export function etfContributorMoves(holdings = [], quotes = {}) {
  return (holdings || [])
    .map((row) => {
      const quote = quotes[row.ticker] || {};
      const change = Number(quote.change_pct_1d);
      const weight = Number(row.weight);
      const contribution =
        Number.isFinite(change) && Number.isFinite(weight) ? (change * weight) / 100 : null;
      return {
        ...row,
        change: Number.isFinite(change) ? change : null,
        contribution,
        last: Number.isFinite(Number(quote.last_price)) ? Number(quote.last_price) : null,
      };
    })
    .sort((a, b) => Math.abs(b.contribution || 0) - Math.abs(a.contribution || 0));
}
