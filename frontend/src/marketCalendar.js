// US equity (NYSE/Nasdaq) trading-session calendar — pure, dependency-free.
//
// Used by the trader view so "freshness" is measured in *trading
// sessions*, not wall-clock: a snapshot generated after Friday's close
// stays current until the next session's close (skipping the weekend
// and any holidays). Regular session is 09:30–16:00 America/New_York;
// a handful of half-days close 13:00 ET.

const DAY_MS = 24 * 60 * 60 * 1000;

// --- America/New_York wall-clock <-> epoch (DST-correct) --------------
function _etParts(ms) {
  const f = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    weekday: "short",
  }).formatToParts(new Date(ms));
  const g = {};
  for (const p of f) g[p.type] = p.value;
  const WD = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  return {
    y: +g.year, m: +g.month, d: +g.day,
    hh: +g.hour, mm: +g.minute, ss: +g.second,
    wd: WD[g.weekday],
  };
}

function _etOffsetMs(ms) {
  const p = _etParts(ms);
  const asUTC = Date.UTC(p.y, p.m - 1, p.d, p.hh, p.mm, p.ss);
  return asUTC - ms; // ET = UTC + offset  =>  offset = asUTC - ms
}

// Epoch (ms) for a given America/New_York wall-clock instant. Two
// iterations converge across DST (offset is only ever ±1h).
export function etEpoch(y, m, d, hh, mm) {
  let guess = Date.UTC(y, m - 1, d, hh, mm, 0);
  for (let i = 0; i < 3; i++) {
    guess = Date.UTC(y, m - 1, d, hh, mm, 0) - _etOffsetMs(guess);
  }
  return guess;
}

// --- holiday math ----------------------------------------------------
function _weekdayUTC(y, m, d) {
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0=Sun..6=Sat
}

function _nthWeekday(y, m, weekday, n) {
  const first = _weekdayUTC(y, m, 1);
  return 1 + ((weekday - first + 7) % 7) + (n - 1) * 7;
}

function _lastWeekday(y, m, weekday) {
  const dim = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const last = _weekdayUTC(y, m, dim);
  return dim - ((last - weekday + 7) % 7);
}

function _easter(y) {
  // Anonymous Gregorian algorithm.
  const a = y % 19, b = Math.floor(y / 100), c = y % 100;
  const dd = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - dd - g + 15) % 30;
  const i = Math.floor(c / 4), k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const mth = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * mth + 114) / 31);
  const day = ((h + l - 7 * mth + 114) % 31) + 1;
  return { m: month, d: day };
}

// Weekend-observance shift for fixed-date holidays. Returns the ET
// [m,d] the market is actually closed, or null if not observed
// (NYSE does not give a Friday off for New Year's Day on a Saturday).
function _observed(y, m, d, isNewYear) {
  const wd = _weekdayUTC(y, m, d);
  if (wd === 6) { // Saturday
    if (isNewYear) return null;
    return d === 1 ? null : [m, d - 1]; // observed prior Friday
  }
  if (wd === 0) { // Sunday -> Monday
    const dim = new Date(Date.UTC(y, m, 0)).getUTCDate();
    return d === dim ? [m + 1 > 12 ? 1 : m + 1, 1] : [m, d + 1];
  }
  return [m, d];
}

const _holidayCache = new Map();

function _fullHolidays(y) {
  if (_holidayCache.has(y)) return _holidayCache.get(y);
  const set = new Set();
  const add = (md) => { if (md) set.add(`${md[0]}-${md[1]}`); };
  add(_observed(y, 1, 1, true));                       // New Year's Day
  set.add(`1-${_nthWeekday(y, 1, 1, 3)}`);             // MLK (3rd Mon Jan)
  set.add(`2-${_nthWeekday(y, 2, 1, 3)}`);             // Presidents (3rd Mon Feb)
  const es = _easter(y);                               // Good Friday
  const gf = new Date(Date.UTC(y, es.m - 1, es.d - 2));
  set.add(`${gf.getUTCMonth() + 1}-${gf.getUTCDate()}`);
  set.add(`5-${_lastWeekday(y, 5, 1)}`);               // Memorial (last Mon May)
  add(_observed(y, 6, 19, false));                     // Juneteenth
  add(_observed(y, 7, 4, false));                      // Independence Day
  set.add(`9-${_nthWeekday(y, 9, 1, 1)}`);             // Labor (1st Mon Sep)
  set.add(`11-${_nthWeekday(y, 11, 4, 4)}`);           // Thanksgiving (4th Thu)
  add(_observed(y, 12, 25, false));                    // Christmas
  _holidayCache.set(y, set);
  return set;
}

function _isTradingDay(p) {
  if (p.wd === 0 || p.wd === 6) return false;
  return !_fullHolidays(p.y).has(`${p.m}-${p.d}`);
}

// Half-days (1:00pm ET close): Black Friday, Christmas Eve, July 3 —
// when each is itself a regular weekday trading day.
function _isEarlyClose(p) {
  const blackFri = _nthWeekday(p.y, 11, 4, 4) + 1; // day after Thanksgiving
  if (p.m === 11 && p.d === blackFri) return true;
  if (p.m === 12 && p.d === 24 && p.wd >= 1 && p.wd <= 5) return true;
  if (p.m === 7 && p.d === 3 && p.wd >= 1 && p.wd <= 5) return true;
  return false;
}

// Close epoch for the session on the ET calendar date of `ms`, or null
// if that date is not a trading day.
function _sessionClose(ms) {
  const p = _etParts(ms);
  if (!_isTradingDay(p)) return null;
  const hh = _isEarlyClose(p) ? 13 : 16;
  return etEpoch(p.y, p.m, p.d, hh, 0);
}

// First trading-session close strictly greater than `ms`.
export function firstCloseAfter(ms) {
  for (let i = 0; i <= 20; i++) {
    const close = _sessionClose(ms + i * DAY_MS);
    if (close !== null && close > ms) return close;
  }
  return ms + DAY_MS; // safety net (should never hit within 20 days)
}

/**
 * Trading-session staleness. A snapshot is:
 *   - "fresh"  until the first session close after it was generated
 *              (so a Fri-after-close run is fresh through Mon's close);
 *   - "warn"   once one session has closed since (≈1 trading day old);
 *   - "stale"  once a second session has closed (≈2+ trading days old).
 *
 * When the snapshot carries an authoritative `market_session`
 * (reported by the generator from the live exchange calendar — it
 * knows holidays, half-days AND unscheduled closures a rule-based
 * calendar can't), its `next_close` is used as the exact fresh→stale
 * boundary. The built-in NYSE calendar is the fallback and powers the
 * softer warn→stale tier.
 *
 * Returns "unknown" for missing/unparseable input.
 */
export function sessionStaleness(refreshedAtISO, opts = {}) {
  // Back-compat: a bare number/Date is treated as `nowMs`.
  if (typeof opts === "number") opts = { nowMs: opts };
  const nowMs = opts.nowMs ?? Date.now();
  const ms = opts.marketSession;
  if (!refreshedAtISO) return "unknown";
  const ts = Date.parse(refreshedAtISO);
  if (!Number.isFinite(ts)) return "unknown";

  let staleAt = null;
  const authNext = ms && ms.next_close ? Date.parse(ms.next_close) : NaN;
  if (Number.isFinite(authNext) && authNext > ts) {
    staleAt = authNext; // authoritative next real session close
  }
  if (staleAt === null) staleAt = firstCloseAfter(ts); // calendar fallback

  if (nowMs < staleAt) return "fresh";
  const warnEnd = firstCloseAfter(staleAt);
  if (nowMs < warnEnd) return "warn";
  return "stale";
}
