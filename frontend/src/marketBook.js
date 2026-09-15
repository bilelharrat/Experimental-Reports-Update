/** Client-side book lots + concentration / day P&L lens. */

import { scheduleDeskSync } from "./deskSync.js";

const LOTS_KEY = "bsh.bookLots";

function readLots() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(LOTS_KEY) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw.map(normalizeLot).filter(Boolean);
  } catch {
    return [];
  }
}

function writeLots(lots) {
  try {
    window.localStorage.setItem(LOTS_KEY, JSON.stringify(lots));
  } catch {
    // ignore
  }
  scheduleDeskSync();
}

function normalizeLot(row) {
  const ticker = String(row?.ticker || "").trim().toUpperCase();
  const shares = Number(row?.shares);
  const cost = Number(row?.cost);
  if (!ticker || !Number.isFinite(shares) || shares <= 0 || !Number.isFinite(cost) || cost < 0) return null;
  return {
    ticker,
    companyId: row?.companyId ? String(row.companyId) : null,
    shares,
    cost,
  };
}

export function loadBookLots() {
  return readLots();
}

export function upsertBookLot({ ticker, shares, cost, companyId = null } = {}) {
  const lot = normalizeLot({ ticker, shares, cost, companyId });
  if (!lot) return readLots();
  const next = readLots().filter((row) => row.ticker !== lot.ticker);
  next.push(lot);
  writeLots(next);
  return next;
}

export function removeBookLot(ticker) {
  const symbol = String(ticker || "").trim().toUpperCase();
  const next = readLots().filter((row) => row.ticker !== symbol);
  writeLots(next);
  return next;
}

/** Mark-to-market P&L for lots using live quote last + day %. */
export function bookPnl(lots = [], quotes = {}) {
  const rows = [];
  let marketValue = 0;
  let costBasis = 0;
  let dayPnl = 0;
  for (const lot of lots || []) {
    const quote = quotes[lot.ticker] || {};
    const last = Number(quote.last_price);
    const change = Number(quote.change_pct_1d);
    const value = Number.isFinite(last) ? last * lot.shares : null;
    const cost = lot.cost * lot.shares;
    const unrealized =
      value != null ? value - cost : null;
    const dayUsd =
      Number.isFinite(last) && Number.isFinite(change)
        ? (last / (1 + change / 100)) * lot.shares * (change / 100)
        : null;
    if (value != null) marketValue += value;
    costBasis += cost;
    if (Number.isFinite(dayUsd)) dayPnl += dayUsd;
    rows.push({
      ticker: lot.ticker,
      companyId: lot.companyId,
      shares: lot.shares,
      cost: lot.cost,
      last: Number.isFinite(last) ? last : null,
      change: Number.isFinite(change) ? change : null,
      marketValue: value,
      costBasis: cost,
      unrealized,
      dayPnl: Number.isFinite(dayUsd) ? dayUsd : null,
    });
  }
  rows.sort((a, b) => Math.abs(b.dayPnl || 0) - Math.abs(a.dayPnl || 0));
  return {
    rows,
    marketValue,
    costBasis,
    unrealized: marketValue - costBasis,
    dayPnl,
  };
}

/** β-weighted book exposure vs a benchmark (default SPY). */
export function bookBetaRisk(lots = [], quotes = {}, { benchTicker = "SPY" } = {}) {
  const pnl = bookPnl(lots, quotes);
  const bench = quotes[String(benchTicker || "SPY").toUpperCase()] || {};
  const benchChange = Number(bench.change_pct_1d);
  let betaNotional = 0;
  let coveredValue = 0;
  const rows = [];
  for (const row of pnl.rows || []) {
    const quote = quotes[row.ticker] || {};
    const beta = Number(quote.beta);
    const value = Number(row.marketValue);
    if (!Number.isFinite(value)) continue;
    const usedBeta = Number.isFinite(beta) ? beta : 1;
    const contribution = value * usedBeta;
    betaNotional += contribution;
    coveredValue += value;
    rows.push({
      ticker: row.ticker,
      marketValue: value,
      beta: Number.isFinite(beta) ? beta : null,
      betaContribution: contribution,
      weight: pnl.marketValue ? value / pnl.marketValue : null,
    });
  }
  const portfolioBeta = coveredValue > 0 ? betaNotional / coveredValue : null;
  const spyEquivalent =
    Number.isFinite(portfolioBeta) && Number.isFinite(pnl.marketValue)
      ? portfolioBeta * pnl.marketValue
      : null;
  const expectedDayPct =
    Number.isFinite(portfolioBeta) && Number.isFinite(benchChange)
      ? portfolioBeta * benchChange
      : null;
  return {
    rows: rows.sort((a, b) => Math.abs(b.betaContribution) - Math.abs(a.betaContribution)),
    marketValue: pnl.marketValue,
    portfolioBeta,
    spyEquivalent,
    expectedDayPct,
    benchTicker: String(benchTicker || "SPY").toUpperCase(),
    benchChange: Number.isFinite(benchChange) ? benchChange : null,
  };
}

/** Sector / beta concentration for followed names with quotes. */
export function bookConcentration(companies = [], quotes = {}) {
  const sectors = new Map();
  let weightedBeta = 0;
  let betaWeight = 0;
  let dayLeaders = [];
  for (const company of companies || []) {
    const ticker = String(company?.ticker || "").trim().toUpperCase();
    if (!ticker) continue;
    const quote = quotes[ticker] || {};
    const last = Number(quote.last_price);
    const change = Number(quote.change_pct_1d);
    const beta = Number(quote.beta ?? company?.trader_snapshot?.price_card?.beta);
    const sector =
      company?.sector ||
      company?.trader_snapshot?.profile?.sector ||
      quote.sector ||
      "Unknown";
    const weight = Number.isFinite(last) ? last : 1;
    sectors.set(sector, (sectors.get(sector) || 0) + weight);
    if (Number.isFinite(beta)) {
      weightedBeta += beta * weight;
      betaWeight += weight;
    }
    if (Number.isFinite(change)) {
      dayLeaders.push({
        ticker,
        name: company.name,
        change,
        companyId: company.id,
      });
    }
  }
  const total = [...sectors.values()].reduce((a, b) => a + b, 0) || 1;
  const sectorMix = [...sectors.entries()]
    .map(([sector, value]) => ({
      sector,
      weight: value / total,
      pct: (value / total) * 100,
    }))
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 6);
  dayLeaders.sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
  return {
    sectorMix,
    avgBeta: betaWeight > 0 ? weightedBeta / betaWeight : null,
    movers: dayLeaders.slice(0, 6),
  };
}
