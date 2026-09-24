// API auth:
//
//   - `fetch` API calls send the per-session bearer token from
//     localStorage (SESSION_KEY) as `Authorization: Bearer <token>`,
//     minted by POST /api/auth/token. `apiFetch` is the canonical wrapper.
//   - Raw-URL requests that can't set headers (downloads via <a href>,
//     EventSource SSE) authenticate via the httponly session cookie the
//     login endpoint sets; `withApiToken(path)` is now just `withBase`.
//
// The old shared-token <meta> flow is removed — it exposed a privileged
// credential in the served HTML.

const SESSION_KEY = "bsh.research.session";

// API path prefix (e.g. "/research") when the app is mounted under one.
// Server injects this in the SPA HTML via <meta name="bsh-research-api-base">
// based on FastAPI's root_path. Empty when the app is at the root. We
// prepend it to every fetched URL so a non-stripping nginx + uvicorn
// (root_path="/research") combo routes correctly.
function getApiBase() {
  if (typeof document === "undefined") return "";
  const el = document.querySelector('meta[name="bsh-research-api-base"]');
  const raw = el?.content ? el.content.trim() : "";
  // Normalize: leading slash, no trailing slash, no double-prefix.
  if (!raw) return "";
  return ("/" + raw.replace(/^\/+|\/+$/g, "")).replace(/^\/$/, "");
}

export function withBase(path) {
  const base = getApiBase();
  if (!base) return path;
  // Avoid double-prefixing if a caller has already supplied an absolute
  // URL or a path that's been through withBase already.
  if (/^https?:\/\//i.test(path)) return path;
  if (path.startsWith(base + "/") || path === base) return path;
  return base + (path.startsWith("/") ? path : "/" + path);
}

function getSessionToken() {
  if (typeof window === "undefined" || !window.localStorage) return null;
  let raw;
  try {
    raw = window.localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  let session;
  try {
    session = JSON.parse(raw);
  } catch {
    window.localStorage.removeItem(SESSION_KEY);
    return null;
  }
  if (!session || !session.token) return null;
  if (session.expires_at) {
    const expiresAt = Date.parse(session.expires_at);
    if (Number.isFinite(expiresAt) && expiresAt <= Date.now()) {
      window.localStorage.removeItem(SESSION_KEY);
      return null;
    }
  }
  return session.token;
}

function getApiToken() {
  // Session token only. The legacy shared-token <meta> tag is gone —
  // it leaked a privileged credential into View Source.
  return getSessionToken();
}

// Formerly appended `?token=<token>` for downloads and SSE, which leaked
// the credential into access logs / history / Referer. Those requests now
// authenticate via the httponly session cookie (set on login), which the
// browser sends automatically on same-origin navigations and EventSource.
// Kept as a thin alias so the call sites don't churn.
export function withApiToken(path) {
  return withBase(path);
}

export function apiFetch(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const tok = getApiToken();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;
  // CSRF marker for any cookie-authenticated mutation (a cross-site page
  // can't set a custom header). Harmless on bearer-authed requests.
  headers["X-BSH-Client"] = "web";
  return fetch(withBase(path), { ...opts, headers, credentials: "same-origin" });
}

function _httpError(status, statusText, body) {
  const err = new Error(`${status} ${statusText}${body ? `: ${body}` : ""}`);
  err.status = status;
  return err;
}

// Shared ok-check for methods that call apiFetch directly (FormData
// uploads, deletes) instead of going through request(). Keeps the two
// paths behaviorally identical: a 401 tears down the stale session via
// bsh:unauthorized, and thrown errors always carry .status (and .detail
// when the body parses as JSON) so callers can branch on them.
async function ensureOk(res) {
  if (res.ok) return res;
  const text = await res.text().catch(() => "");
  if (res.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("bsh:unauthorized"));
  }
  const err = _httpError(res.status, res.statusText, text);
  try {
    err.detail = JSON.parse(text);
  } catch {
    /* body wasn't JSON — err.message already carries the raw text */
  }
  throw err;
}

async function request(path, opts = {}) {
  const { timeoutMs, ...fetchOpts } = opts;
  let timeoutId = null;
  let controller = null;
  if (timeoutMs && !fetchOpts.signal) {
    controller = new AbortController();
    fetchOpts.signal = controller.signal;
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }
  const res = await apiFetch(path, {
    headers: { "Content-Type": "application/json", ...(fetchOpts.headers || {}) },
    ...fetchOpts,
  }).catch((e) => {
    if (e?.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw e;
  }).finally(() => {
    if (timeoutId != null) window.clearTimeout(timeoutId);
  });
  // auth.js listens for the 401-triggered bsh:unauthorized event inside
  // ensureOk and clears the stale session so the router guard kicks the
  // user back to /login on next nav.
  await ensureOk(res);
  if (res.status === 204) return null;
  return res.json();
}

async function _publicCall(path, init) {
  const res = await fetch(withBase(path), init);
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = j?.detail || "";
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw _httpError(res.status, res.statusText, detail);
  }
  return res.status === 204 ? null : res.json();
}

/** POST to an endpoint that is reachable without a session. */
function publicPost(path, body) {
  return _publicCall(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  // --- Auth ---
  // login() is the only call that runs without a bearer header (it IS
  // what mints the token). All other /api/* calls go through apiFetch.
  login: async (email, password) => {
    const res = await fetch(withBase("/api/auth/token"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      let detail = "";
      try {
        const j = await res.json();
        detail = j?.detail || "";
      } catch {
        detail = await res.text().catch(() => "");
      }
      throw _httpError(res.status, res.statusText, detail);
    }
    return res.json();
  },
  me: () => request("/api/auth/me"),
  logout: () =>
    request("/api/auth/logout", { method: "POST" }),

  // The three public forms. Like login() they run without a bearer
  // header, because the caller has no session yet by definition.
  register: (email, password) =>
    publicPost("/api/auth/register", { email, password }),
  requestPasswordReset: (email) =>
    publicPost("/api/auth/reset/request", { email }),
  checkResetToken: (token) => publicPost("/api/auth/reset/check", { token }),
  consumePasswordReset: (token, newPassword) =>
    publicPost("/api/auth/reset/consume", { token, new_password: newPassword }),

  // Account administration (admin only, server-enforced).
  listAccounts: () => request("/api/auth/accounts"),
  approveAccount: (email, role) =>
    request(`/api/auth/accounts/${encodeURIComponent(email)}/approve`, {
      method: "POST",
      body: JSON.stringify({ role }),
    }),
  disableAccount: (email) =>
    request(`/api/auth/accounts/${encodeURIComponent(email)}/disable`, {
      method: "POST",
    }),
  mintResetLink: (email) =>
    request(`/api/auth/accounts/${encodeURIComponent(email)}/reset-link`, {
      method: "POST",
    }),

  changePassword: (currentPassword, newPassword) =>
    request("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),
  listSessions: () => request("/api/auth/sessions"),
  revokeSessions: (sessionId) =>
    request(
      `/api/auth/sessions/revoke${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`,
      { method: "POST" },
    ),

  options: () => request("/api/options"),
  listCompanies: () => request("/api/companies"),
  deleteCompany: (id) =>
    request(`/api/companies/${id}`, { method: "DELETE" }),
  listTrackingUpdates: (companyId) =>
    request(`/api/companies/${companyId}/tracking-updates`),
  syncTrackingUpdates: (companyId, body = {}) =>
    request(`/api/companies/${companyId}/tracking-updates/sync`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  executeTrackingAutoRun: (companyId, autoRunId, body = {}) =>
    request(
      `/api/companies/${companyId}/tracking-updates/auto-runs/${autoRunId}/execute`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  decisionRecords: {
    list: (companyId) => request(`/api/companies/${companyId}/decisions`),
    add: (companyId, payload) =>
      request(`/api/companies/${companyId}/decisions`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    remove: (companyId, decisionId) =>
      request(
        `/api/companies/${companyId}/decisions/${encodeURIComponent(decisionId)}`,
        { method: "DELETE" },
      ),
  },
  getTrackingWatchlist: () => request("/api/tracking/watchlist"),
  putTrackingWatchlist: (body) =>
    request("/api/tracking/watchlist", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  syncAllTrackingUpdates: (body = {}) =>
    request("/api/tracking/sync-all", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // The cadence bar shared by every background job that spends tokens.
  getAutoUpdates: () => request("/api/auto-updates"),
  putAutoUpdate: (channelId, body) =>
    request(`/api/auto-updates/${encodeURIComponent(channelId)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  // Background sync schedule and the global auto-apply switch.
  getTrackingSettings: () => request("/api/tracking/settings"),
  putTrackingSettings: (body) =>
    request("/api/tracking/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  // Tracking dashboard: the follow list is browser-local, so the ids ride
  // along as query params rather than the server keeping a watchlist.
  trackingRollup: (companyIds = []) => {
    const ids = (companyIds || []).map((id) => String(id)).filter(Boolean);
    if (ids.length === 0) return Promise.resolve(null);
    const qs = ids
      .map((id) => `company_id=${encodeURIComponent(id)}`)
      .join("&");
    return request(`/api/tracking/rollup?${qs}`, { timeoutMs: 20000 });
  },
    liveQuotes: (tickers = []) => {
    const symbols = (tickers || [])
      .map((ticker) => String(ticker || "").trim())
      .filter(Boolean);
    if (symbols.length === 0) return Promise.resolve({ quotes: {} });
    const qs = symbols
      .map((ticker) => `ticker=${encodeURIComponent(ticker)}`)
      .join("&");
    return request(`/api/quotes?${qs}`, { timeoutMs: 12000 });
  },
  quotesNews: ({ tickers = [], limit = 40 } = {}) => {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    for (const ticker of tickers || []) {
      const symbol = String(ticker || "").trim();
      if (symbol) params.append("ticker", symbol);
    }
    return request(`/api/quotes/news?${params}`, { timeoutMs: 15000 });
  },
  getNewsBrief: ({ title, company = null, lang = "en" } = {}) => {
    const params = new URLSearchParams({
      title: String(title || ""),
      lang: String(lang || "en"),
    });
    if (company) params.set("company", String(company));
    return request(`/api/news/brief?${params}`, { timeoutMs: 10000 });
  },
  // refresh:false never calls Claude (cached AI brief or a basic brief);
  // refresh:true is the warned rewrite, which may queue behind a refresh.
  postNewsBrief: (body) =>
    request("/api/news/brief", {
      method: "POST",
      body: JSON.stringify(body || {}),
      timeoutMs: 300000,
    }),
  newsBriefRefreshStatus: () =>
    request("/api/news/brief/refresh", { timeoutMs: 10000 }),
  startNewsBriefRefresh: (body) =>
    request("/api/news/brief/refresh", {
      method: "POST",
      body: JSON.stringify(body || {}),
      timeoutMs: 15000,
    }),
  prewarmNewsBriefs: (body) =>
    request("/api/news/brief/prewarm", {
      method: "POST",
      body: JSON.stringify(body || {}),
      timeoutMs: 15000,
    }),
  newsBriefStatuses: (body) =>
    request("/api/news/brief/status", {
      method: "POST",
      body: JSON.stringify(body || {}),
      timeoutMs: 10000,
    }),
  registerDeviceToken: (body) =>
    request("/api/device-tokens", {
      method: "POST",
      body: JSON.stringify(body || {}),
      timeoutMs: 8000,
    }),
  quoteChart: (ticker, range = "1d") =>
    request(
      `/api/quotes/${encodeURIComponent(ticker)}/chart?range=${encodeURIComponent(range)}`,
      { timeoutMs: 15000 },
    ),
  quoteSearch: (q) =>
    request(`/api/quotes/search?q=${encodeURIComponent(q)}`, { timeoutMs: 8000 }),
  quoteWorkspace: (ticker) =>
    request(`/api/quotes/${encodeURIComponent(ticker)}/workspace`, { timeoutMs: 20000 }),
  quoteScreeners: () => request("/api/quotes/screeners", { timeoutMs: 20000 }),
  quoteCalendar: (tickers = []) => {
    const symbols = (tickers || [])
      .map((ticker) => String(ticker || "").trim())
      .filter(Boolean);
    const qs = symbols
      .map((ticker) => `ticker=${encodeURIComponent(ticker)}`)
      .join("&");
    return request(
      `/api/quotes/calendar${qs ? `?${qs}` : ""}`,
      { timeoutMs: 25000 },
    );
  },
  quotePeers: (ticker, peers = []) => {
    const qs = (peers || [])
      .map((peer) => `peer=${encodeURIComponent(peer)}`)
      .join("&");
    return request(
      `/api/quotes/${encodeURIComponent(ticker)}/peers${qs ? `?${qs}` : ""}`,
      { timeoutMs: 25000 },
    );
  },
  deskPrefs: () => request("/api/desk/prefs", { timeoutMs: 10000 }),
  saveDeskPrefs: (data) =>
    request("/api/desk/prefs", {
      method: "PUT",
      body: JSON.stringify({ data }),
      timeoutMs: 10000,
    }),
  alertEvents: (since = null, limit = 100) => {
    const params = new URLSearchParams();
    if (since) params.set("since", since);
    params.set("limit", String(limit));
    return request(`/api/alerts/events?${params}`, { timeoutMs: 10000 });
  },
  recordAlertEvents: (events = []) =>
    request("/api/alerts/events", {
      method: "POST",
      body: JSON.stringify({ events }),
      timeoutMs: 10000,
    }),
  runAlertCheck: () =>
    request("/api/alerts/check", { method: "POST", timeoutMs: 20000 }),
  signalLedger: () => request("/api/signals/ledger", { timeoutMs: 20000 }),
  recordSignal: (entry) =>
    request("/api/signals/ledger", {
      method: "POST",
      body: JSON.stringify(entry),
      timeoutMs: 15000,
    }),
  deleteSignal: (id) =>
    request(`/api/signals/ledger/${encodeURIComponent(id)}`, {
      method: "DELETE",
      timeoutMs: 10000,
    }),
  marketBrief: (date = null) =>
    request(`/api/market-brief${date ? `?date=${encodeURIComponent(date)}` : ""}`, {
      timeoutMs: 15000,
    }),
  marketBriefSchedule: () => request("/api/market-brief/schedule", { timeoutMs: 10000 }),
  marketBriefArchive: () => request("/api/market-brief/archive", { timeoutMs: 10000 }),
  runMarketBrief: () =>
    request("/api/market-brief/run", { method: "POST", timeoutMs: 45000 }),
  writeMarketBriefNote: (date = null, length = "short") =>
    request("/api/market-brief/note", {
      method: "POST",
      body: JSON.stringify({ ...(date ? { date } : {}), length }),
      timeoutMs: length === "long" ? 480000 : 200000,
    }),
  quotesDiagnostics: () => request("/api/diagnostics/quotes", { timeoutMs: 10000 }),
  listReports: () => request("/api/reports"),
  getReport: (id) => request(`/api/reports/${id}`),
  getReportAnnotations: (id, { includeDrawing = false, includeOverlay = false } = {}) => {
    const qs = new URLSearchParams();
    qs.set("include_drawing", includeDrawing ? "true" : "false");
    qs.set("include_overlay", includeOverlay ? "true" : "false");
    return request(`/api/reports/${id}/annotations?${qs}`, { timeoutMs: 15000 });
  },
  putReportAnnotations: (id, body) =>
    request(`/api/reports/${id}/annotations`, {
      method: "PUT",
      body: JSON.stringify(body),
      timeoutMs: 30000,
    }),
  deleteReportAnnotations: (id) =>
    request(`/api/reports/${id}/annotations`, { method: "DELETE", timeoutMs: 10000 }),
  reportAnnotationOverlayUrl: (id) =>
    withApiToken(`/api/reports/${id}/annotations/overlay.png`),
  autocompleteCompanies: (q) =>
    request(`/api/companies/autocomplete?q=${encodeURIComponent(q)}`),
  deepSearchCompanies: (q, { refresh = false } = {}) =>
    request(
      `/api/companies/search?q=${encodeURIComponent(q)}${
        refresh ? "&refresh=true" : ""
      }`,
    ),
  startDeepSearch: (q, { refresh = false } = {}) =>
    request(
      `/api/companies/search/start?q=${encodeURIComponent(q)}${
        refresh ? "&refresh=true" : ""
      }`,
      { method: "POST" },
    ),
  searchStreamUrl: (jobId) =>
    withApiToken(`/api/companies/search/stream/${jobId}`),
  selectCompany: (payload) =>
    request("/api/companies/select", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getCompany: (id) => request(`/api/companies/${id}`),
  getCompanyNewsFeed: (id, filters = {}) => {
    const qs = new URLSearchParams();
    if (filters.category) qs.set("category", filters.category);
    if (filters.tag) qs.set("tag", filters.tag);
    if (filters.search) qs.set("search", filters.search);
    if (filters.lang) qs.set("lang", filters.lang);
    const query = qs.toString();
    return request(`/api/companies/${id}/news-feed${query ? `?${query}` : ""}`);
  },
  refreshCompanyNewsFeed: (id, lang) => {
    const qs = lang ? `?lang=${encodeURIComponent(lang)}` : "";
    return request(`/api/companies/${id}/news-feed/refresh${qs}`, { method: "POST" });
  },
  getCompanyIndustryView: (id) =>
    request(`/api/companies/${id}/industry-view`),
  getCompanyProfile: (companyId, { quote = true } = {}) =>
    request(`/api/companies/${companyId}/profile?quote=${quote ? "true" : "false"}`),
  // A listed company's next earnings date, recent quarters against
  // estimates, and SEC filings (server/filings_watch.for_ticker).
  getCompanyEarningsFilings: (companyId, { refresh = false } = {}) =>
    request(
      `/api/companies/${companyId}/earnings-filings${refresh ? "?refresh=true" : ""}`,
    ),
  getDealPipeline: (companyId) =>
    request(`/api/companies/${companyId}/deal-pipeline`),
  updateDealPipeline: (companyId, payload) =>
    request(`/api/companies/${companyId}/deal-pipeline`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getCapModel: (companyId) =>
    request(`/api/companies/${companyId}/cap-model`),
  saveCapModel: (companyId, inputs) =>
    request(`/api/companies/${companyId}/cap-model`, {
      method: "PUT",
      body: JSON.stringify(inputs),
    }),
  getCompanyComps: (companyId, refresh = false) =>
    request(`/api/companies/${companyId}/comps${refresh ? "?refresh=1" : ""}`),
  saveCompsPeers: (companyId, tickers) =>
    request(`/api/companies/${companyId}/comps/peers`, {
      method: "PUT",
      body: JSON.stringify({ tickers }),
    }),
  getFounderDossier: (companyId) =>
    request(`/api/companies/${companyId}/founder-dossier`),
  deepSearchFounder: (companyId) =>
    request(`/api/companies/${companyId}/founder-dossier/deep-search`, {
      method: "POST",
    }),
  getMemoNumberLint: (companyId) =>
    request(`/api/companies/${companyId}/memo-number-lint`),
  getFactLedger: (companyId) =>
    request(`/api/companies/${companyId}/fact-ledger`),
  putFactLedger: (companyId, text) =>
    request(`/api/companies/${companyId}/fact-ledger`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
  getSourceCache: (companyId) =>
    request(`/api/companies/${companyId}/source-cache`),
  getReportFactCheck: (reportId) =>
    request(`/api/reports/${reportId}/fact-check`),
  getSignalScore: (companyId) =>
    request(`/api/companies/${companyId}/signal-score`),
  intakeDeck: async ({ file, companyId, companyName }) => {
    const fd = new FormData();
    fd.append("file", file);
    if (companyId) fd.append("company_id", companyId);
    if (companyName) fd.append("company_name", companyName);
    const res = await ensureOk(
      await apiFetch("/api/intake/decks", {
        method: "POST",
        body: fd,
      }),
    );
    return res.json();
  },
  getICMeetings: (companyId) =>
    request(`/api/companies/${companyId}/ic/meetings`),
  openICMeeting: (companyId, payload) =>
    request(`/api/companies/${companyId}/ic/meetings`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  castICVote: (companyId, meetingId, payload) =>
    request(`/api/companies/${companyId}/ic/meetings/${meetingId}/votes`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  closeICMeeting: (companyId, meetingId, payload) =>
    request(`/api/companies/${companyId}/ic/meetings/${meetingId}/close`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getReferenceCalls: (companyId) =>
    request(`/api/companies/${companyId}/reference-calls`),
  addReferenceCall: (companyId, payload) =>
    request(`/api/companies/${companyId}/reference-calls`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteReferenceCall: (companyId, itemId) =>
    request(`/api/companies/${companyId}/reference-calls/${itemId}`, {
      method: "DELETE",
    }),
  getICComparables: (companyId) =>
    request(`/api/companies/${companyId}/ic/comparables`),
  getRedTeam: (companyId) =>
    request(`/api/companies/${companyId}/ic/red-team`),
  startRedTeam: (companyId) =>
    request(`/api/companies/${companyId}/ic/red-team`, {
      method: "POST",
    }),
  getCompanyComments: (companyId) =>
    request(`/api/companies/${companyId}/comments`),
  addCompanyComment: (companyId, payload) =>
    request(`/api/companies/${companyId}/comments`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  resolveCompanyComment: (companyId, commentId, resolved = true) =>
    request(
      `/api/companies/${companyId}/comments/${encodeURIComponent(commentId)}/resolve`,
      { method: "POST", body: JSON.stringify({ resolved }) },
    ),
  deleteCompanyComment: (companyId, commentId) =>
    request(
      `/api/companies/${companyId}/comments/${encodeURIComponent(commentId)}`,
      { method: "DELETE" },
    ),
  getChatChannels: () => request("/api/chat/channels"),
  getMemoAnalysis: (companyId) =>
    request(`/api/companies/${companyId}/memo-analysis`),
  getEvidence: (companyId) =>
    request(`/api/companies/${companyId}/evidence`),
  getSignalMoves: () =>
    request("/api/signal-watch"),
  getCompetitorDetail: (companyId, competitorId) =>
    request(
      `/api/companies/${companyId}/competitors/${encodeURIComponent(competitorId)}`,
    ),
  workspaceSettings: () => request("/api/workspace/settings"),
  updateWorkspaceSettings: (patch) =>
    request("/api/workspace/settings", {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  userCenter: () => request("/api/workspace/user-center"),
  analyticsSummary: () => request("/api/analytics/summary"),
  refreshCompany: (id) =>
    request(`/api/companies/${id}/refresh`, { method: "POST" }),
  regenAllCompanies: ({ force = false } = {}) => {
    const qs = force ? "?force=true" : "";
    return request(`/api/companies/regen-all${qs}`, {
      method: "POST",
      timeoutMs: 15000,
    });
  },
  regenAllCompaniesStreamUrl: () =>
    withApiToken("/api/companies/regen-all/stream"),
  regenAllCompaniesStatus: () =>
    request("/api/companies/regen-all/status", { timeoutMs: 8000 }),
  generateReport: (payload) =>
    request("/api/reports", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  studioInvestigate: (payload) =>
    request("/api/memos/studio/investigate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  studioGenerate: (reportId) =>
    request(`/api/memos/studio/${encodeURIComponent(reportId)}/generate`, {
      method: "POST",
    }),
  resumeReport: (reportId) =>
    request(`/api/reports/${encodeURIComponent(reportId)}/resume`, {
      method: "POST",
    }),
  dismissReport: (reportId) =>
    request(`/api/reports/${encodeURIComponent(reportId)}/dismiss`, {
      method: "POST",
    }),
  cancelReportRun: (reportId) =>
    request(`/api/reports/${encodeURIComponent(reportId)}/cancel`, {
      method: "POST",
    }),
  cancelResearchFileSummary: (companyId, fileId) =>
    request(
      `/api/companies/${companyId}/research-files/${encodeURIComponent(fileId)}/summary/cancel`,
      { method: "POST" },
    ),
  cancelExternalResearchAnalysis: (itemId) =>
    request(`/api/external/research/${encodeURIComponent(itemId)}/analysis/cancel`, {
      method: "POST",
    }),
  cancelExternalTranslation: (itemId) =>
    request(`/api/external/research/${encodeURIComponent(itemId)}/translate/cancel`, {
      method: "POST",
    }),
  deleteReport: async (reportId) => {
    await ensureOk(
      await apiFetch(`/api/reports/${encodeURIComponent(reportId)}`, {
        method: "DELETE",
      }),
    );
  },
  listCompanyReports: (companyId) =>
    request(`/api/companies/${companyId}/reports`),
  // A report's versions, review, comments and files (server/api.py).
  getReportDiff: (reportId, againstId) => {
    const qs = againstId ? `?against=${encodeURIComponent(againstId)}` : "";
    return request(`/api/reports/${encodeURIComponent(reportId)}/diff${qs}`);
  },
  setReportReview: (reportId, { state, note, force, acknowledgeOpenComments } = {}) =>
    request(`/api/reports/${encodeURIComponent(reportId)}/review`, {
      method: "PATCH",
      body: JSON.stringify({
        state,
        ...(note ? { note } : {}),
        ...(force ? { force: true } : {}),
        ...(acknowledgeOpenComments ? { acknowledge_open_comments: true } : {}),
      }),
    }),
  listReportComments: (reportId, { openOnly = false, flagsOnly = false } = {}) => {
    const params = new URLSearchParams();
    if (openOnly) params.set("open_only", "true");
    if (flagsOnly) params.set("flags_only", "true");
    const qs = params.toString();
    return request(
      `/api/reports/${encodeURIComponent(reportId)}/comments${qs ? `?${qs}` : ""}`,
    );
  },
  addReportComment: (reportId, payload) =>
    request(`/api/reports/${encodeURIComponent(reportId)}/comments`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  resolveReportComment: (reportId, commentId) =>
    request(
      `/api/reports/${encodeURIComponent(reportId)}/comments/${encodeURIComponent(commentId)}/resolve`,
      { method: "POST" },
    ),
  recordReportEvent: (reportId, event, { language, source } = {}) =>
    request(`/api/reports/${encodeURIComponent(reportId)}/events`, {
      method: "POST",
      body: JSON.stringify({
        event,
        ...(language ? { language } : {}),
        ...(source ? { source } : {}),
      }),
      timeoutMs: 8000,
    }),
  reportReadiness: (companyId, engine) => {
    const params = new URLSearchParams({ company_id: companyId });
    if (engine) params.set("engine", engine);
    return request(`/api/reports/readiness?${params}`, { timeoutMs: 10000 });
  },
  reportEstimates: () => request("/api/reports/estimates", { timeoutMs: 10000 }),
  // PDF rendition, inline. 503 + Retry-After while it is being made.
  reportPdfUrl: (reportId, language = "en", artifact = "memo") =>
    withApiToken(
      `/api/reports/${encodeURIComponent(reportId)}/preview?language=${encodeURIComponent(language)}&artifact=${encodeURIComponent(artifact)}`,
    ),
  // An explicit Download: purpose=export is what the export log records.
  reportExportUrl: (reportId, language = "en", artifact = "memo") =>
    withApiToken(
      `/api/reports/${encodeURIComponent(reportId)}/download?language=${encodeURIComponent(language)}&artifact=${encodeURIComponent(artifact)}&purpose=export`,
    ),
  reportBundleUrl: (reportId, format = "all") =>
    withApiToken(
      `/api/reports/${encodeURIComponent(reportId)}/bundle?format=${encodeURIComponent(format)}`,
    ),
  getFundPolicy: () => request("/api/settings/fund-policy"),
  updateFundPolicy: (policy) =>
    request("/api/settings/fund-policy", {
      method: "PUT",
      body: JSON.stringify(policy),
    }),
  listCompanyDocuments: (companyId) =>
    request(`/api/companies/${companyId}/documents`),
  updateDocumentMetadata: (companyId, backend, documentId, patch) =>
    request(
      `/api/companies/${companyId}/documents/${encodeURIComponent(backend)}/${encodeURIComponent(documentId)}`,
      { method: "PATCH", body: JSON.stringify(patch) },
    ),
  setDocumentUseInReport: (companyId, backend, documentId, useInReport) =>
    request(
      `/api/companies/${companyId}/documents/${encodeURIComponent(backend)}/${encodeURIComponent(documentId)}/use-in-report`,
      { method: "POST", body: JSON.stringify({ use_in_report: useInReport }) },
    ),
  listUnresolvedIntake: (companyId = null) =>
    request(
      `/api/intake/unresolved${companyId ? `?company_id=${encodeURIComponent(companyId)}` : ""}`,
    ),
  listFiles: (companyId) => request(`/api/companies/${companyId}/files`),
  uploadFile: async (companyId, file, label, language) => {
    const fd = new FormData();
    fd.append("file", file);
    if (label) fd.append("label", label);
    if (language) fd.append("language", language);
    const res = await ensureOk(
      await apiFetch(`/api/companies/${companyId}/files`, {
        method: "POST",
        body: fd,
      }),
    );
    return res.json();
  },
  fileUrl: (companyId, fileId) =>
    withApiToken(`/api/companies/${companyId}/files/${fileId}`),
  filePreviewUrl: (companyId, fileId) =>
    withApiToken(`/api/companies/${companyId}/files/${fileId}/preview`),
  deleteFile: async (companyId, fileId) => {
    await ensureOk(
      await apiFetch(`/api/companies/${companyId}/files/${fileId}`, {
        method: "DELETE",
      }),
    );
  },
  getFileSummary: (companyId, fileId) =>
    request(`/api/companies/${companyId}/files/${fileId}/summary`),
  generateFileSummary: (companyId, fileId, { speed = "auto" } = {}) =>
    request(
      `/api/companies/${companyId}/files/${fileId}/summary?speed=${encodeURIComponent(speed)}`,
      { method: "POST" },
    ),
  fileSummaryStreamUrl: (companyId, fileId) =>
    withApiToken(
      `/api/companies/${companyId}/files/${fileId}/summary/stream`,
    ),
  listActiveJobs: () => request("/api/jobs/active", { timeoutMs: 8000 }),
  listJobHistory: (limit = 30) =>
    request(`/api/jobs/history?limit=${encodeURIComponent(limit)}`, {
      timeoutMs: 8000,
    }),
  jobLog: (logUrl) => request(logUrl, { timeoutMs: 8000 }),
  deleteFileSummary: async (companyId, fileId) => {
    await ensureOk(
      await apiFetch(`/api/companies/${companyId}/files/${fileId}/summary`, {
        method: "DELETE",
      }),
    );
  },

  // Research library (Serena's per-company background-docs folder).
  // Distinct from the Document Library above.
  listResearchFiles: (companyId) =>
    request(`/api/companies/${companyId}/research-files`),
  uploadResearchFile: async (companyId, file, label, extra = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (label) fd.append("label", label);
    // Folder handshake: the first member sends folder_name only; the
    // response carries the server-minted folder_id the rest echo back.
    if (extra.folder_name) fd.append("folder_name", extra.folder_name);
    if (extra.folder_id) fd.append("folder_id", extra.folder_id);
    const res = await ensureOk(
      await apiFetch(`/api/companies/${companyId}/research-files`, {
        method: "POST",
        body: fd,
      }),
    );
    return res.json();
  },
  analyzeResearchFile: (companyId, targetId) =>
    request(
      `/api/companies/${companyId}/research-files/${encodeURIComponent(targetId)}/analysis`,
      { method: "POST" },
    ),
  cancelResearchFileAnalysis: (companyId, targetId) =>
    request(
      `/api/companies/${companyId}/research-files/${encodeURIComponent(targetId)}/analysis/cancel`,
      { method: "POST" },
    ),
  researchFileAnalysisStreamUrl: (companyId, targetId) =>
    withApiToken(
      `/api/companies/${companyId}/research-files/${encodeURIComponent(targetId)}/analysis/stream`,
    ),
  researchFileUrl: (companyId, fileId, opts = {}) =>
    withApiToken(
      `/api/companies/${companyId}/research-files/${fileId}${
        opts.inline ? "?inline=1" : ""
      }`,
    ),
  deleteResearchFile: async (companyId, fileId) => {
    await ensureOk(
      await apiFetch(`/api/companies/${companyId}/research-files/${fileId}`, {
        method: "DELETE",
      }),
    );
  },
  generateResearchFileSummary: (companyId, fileId) =>
    request(
      `/api/companies/${companyId}/research-files/${fileId}/summary`,
      { method: "POST" },
    ),
  researchFileSummaryStreamUrl: (companyId, fileId) =>
    withApiToken(
      `/api/companies/${companyId}/research-files/${fileId}/summary/stream`,
    ),
  deleteResearchFileSummary: async (companyId, fileId) => {
    await ensureOk(
      await apiFetch(
        `/api/companies/${companyId}/research-files/${fileId}/summary`,
        { method: "DELETE" },
      ),
    );
  },

  memoAnalysis: {
    // `create: false` reads without starting a session when there is none.
    get: (companyId, { create = true } = {}) =>
      request(
        `/api/companies/${companyId}/memo-analysis${create ? "" : "?create=false"}`,
      ),
    getCatalog: (companyId) =>
      request(`/api/companies/${companyId}/memo-analysis/catalog`),
    runLedger: (companyId) =>
      request(`/api/companies/${companyId}/memo-analysis/run-ledger`, { timeoutMs: 15000 }),
    runTool: (companyId, toolName) =>
      request(
        `/api/companies/${companyId}/memo-analysis/tools/${encodeURIComponent(toolName)}/run`,
        { method: "POST", timeoutMs: 30000 },
      ),
    patchArtifact: (companyId, artifactName, patch) =>
      request(
        `/api/companies/${companyId}/memo-analysis/artifacts/${encodeURIComponent(artifactName)}`,
        { method: "PATCH", body: JSON.stringify(patch) },
      ),
    refineRisk: (companyId, riskId, body) =>
      request(
        `/api/companies/${companyId}/memo-analysis/risks/${encodeURIComponent(riskId)}/refine`,
        { method: "POST", body: JSON.stringify(body || {}) },
      ),
    patchTask: (companyId, taskId, patch) =>
      request(
        `/api/companies/${companyId}/memo-analysis/research-tasks/${encodeURIComponent(taskId)}`,
        { method: "PATCH", body: JSON.stringify(patch) },
      ),
    runTask: (companyId, taskId) =>
      request(
        `/api/companies/${companyId}/memo-analysis/research-tasks/${encodeURIComponent(taskId)}/run`,
        { method: "POST", timeoutMs: 30000 },
      ),
    runSelectedTasks: (companyId, retryFailed = true) =>
      request(
        `/api/companies/${companyId}/memo-analysis/research-tasks/run-selected?retry_failed=${retryFailed ? "true" : "false"}`,
        { method: "POST", timeoutMs: 30000 },
      ),
    cancelTask: (companyId, taskId) =>
      request(
        `/api/companies/${companyId}/memo-analysis/research-tasks/${encodeURIComponent(taskId)}/cancel`,
        { method: "POST" },
      ),
    getEvidenceMatrix: (companyId) =>
      request(`/api/companies/${companyId}/evidence-matrix`),
    approve: (companyId) =>
      request(`/api/companies/${companyId}/memo-analysis/approve`, {
        method: "POST",
      }),
  },

  memoEditor: {
    get: (companyId) =>
      request(`/api/companies/${companyId}/memo-editor`),
    patchCard: (companyId, sectionId, cardId, patch) =>
      request(
        `/api/companies/${companyId}/memo-editor/sections/${encodeURIComponent(sectionId)}/cards/${encodeURIComponent(cardId)}`,
        { method: "PATCH", body: JSON.stringify(patch) },
      ),
    addCard: (companyId, sectionId, payload) =>
      request(
        `/api/companies/${companyId}/memo-editor/sections/${encodeURIComponent(sectionId)}/cards`,
        { method: "POST", body: JSON.stringify(payload) },
      ),
    deleteCard: (companyId, sectionId, cardId) =>
      request(
        `/api/companies/${companyId}/memo-editor/sections/${encodeURIComponent(sectionId)}/cards/${encodeURIComponent(cardId)}`,
        { method: "DELETE" },
      ),
    moveCard: (companyId, sectionId, cardId, direction) =>
      request(
        `/api/companies/${companyId}/memo-editor/sections/${encodeURIComponent(sectionId)}/cards/${encodeURIComponent(cardId)}/move`,
        { method: "POST", body: JSON.stringify({ direction }) },
      ),
    reorderCards: (companyId, sectionId, orderedIds) =>
      request(
        `/api/companies/${companyId}/memo-editor/sections/${encodeURIComponent(sectionId)}/cards/reorder`,
        { method: "POST", body: JSON.stringify({ ordered_ids: orderedIds }) },
      ),
    patchBullet: (companyId, sectionId, cardId, bulletId, patch) =>
      request(
        `/api/companies/${companyId}/memo-editor/sections/${encodeURIComponent(sectionId)}/cards/${encodeURIComponent(cardId)}/bullets/${encodeURIComponent(bulletId)}`,
        { method: "PATCH", body: JSON.stringify(patch) },
      ),
    diveDeeper: (companyId, sectionId, cardId, bulletId, text = null) =>
      request(
        `/api/companies/${companyId}/memo-editor/sections/${encodeURIComponent(sectionId)}/cards/${encodeURIComponent(cardId)}/bullets/${encodeURIComponent(bulletId)}/dive-deeper`,
        { method: "POST", body: JSON.stringify({ text }) },
      ),
    selectConclusion: (companyId, conclusionId) =>
      request(`/api/companies/${companyId}/memo-editor/conclusion/select`, {
        method: "POST",
        body: JSON.stringify({ conclusion_id: conclusionId }),
      }),
    rerunSection: (companyId, sectionId) =>
      request(
        `/api/companies/${companyId}/memo-editor/sections/${encodeURIComponent(sectionId)}/rerun`,
        { method: "POST" },
      ),
    patchAppendixBlock: (companyId, blockId, patch) =>
      request(
        `/api/companies/${companyId}/memo-editor/appendix/${encodeURIComponent(blockId)}`,
        { method: "PATCH", body: JSON.stringify(patch) },
      ),
    exportProjection: (companyId, { record = false } = {}) =>
      request(`/api/companies/${companyId}/memo-editor/export-projection`, {
        method: record ? "POST" : "GET",
      }),
    history: (companyId) =>
      request(`/api/companies/${companyId}/memo-editor/history`),
    revision: (companyId, revisionId) =>
      request(
        `/api/companies/${companyId}/memo-editor/history/${encodeURIComponent(revisionId)}`,
      ),
    createTask: (companyId, payload) =>
      request(`/api/companies/${companyId}/memo-editor/tasks`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    updateTask: (companyId, taskId, patch) =>
      request(
        `/api/companies/${companyId}/memo-editor/tasks/${encodeURIComponent(taskId)}`,
        { method: "PATCH", body: JSON.stringify(patch) },
      ),
  },

  // External news, research, and Hormuz
  externalFeed: () => request("/api/external/feed"),
  listNews: () => request("/api/external/news"),
  getNews: (id) => request(`/api/external/news/${id}`),
  createNews: (url) =>
    request("/api/external/news", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  linkPreview: (url) =>
    request("/api/external/link-preview", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  newsArchiveUrl: (id) => withApiToken(`/api/external/news/${id}/archive`),
  deleteNews: async (id) => {
    await ensureOk(
      await apiFetch(`/api/external/news/${id}`, { method: "DELETE" }),
    );
  },
  retryNews: (id) =>
    request(`/api/external/news/${id}/retry`, { method: "POST" }),
  retryExternalResearch: (id) =>
    request(`/api/external/research/${id}/retry`, { method: "POST" }),
  diagnostics: () => request("/api/diagnostics"),
  listExternalResearch: () => request("/api/external/research"),
  getExternalResearch: (id) => request(`/api/external/research/${id}`),
  uploadExternalResearch: async (form) => {
    const res = await ensureOk(
      await apiFetch("/api/external/research", { method: "POST", body: form }),
    );
    return res.json();
  },
  externalResearchFileUrl: (id, opts = {}) =>
    withApiToken(
      `/api/external/research/${id}/file${opts.inline ? "?inline=1" : ""}`,
    ),
  deleteExternalResearch: async (id) => {
    await ensureOk(
      await apiFetch(`/api/external/research/${id}`, { method: "DELETE" }),
    );
  },
  startResearchTranslation: (id, appLanguage) =>
    request(
      `/api/external/research/${id}/translate${
        appLanguage ? `?app_language=${encodeURIComponent(appLanguage)}` : ""
      }`,
      { method: "POST" },
    ),
  getResearchTranslation: (id) =>
    request(`/api/external/research/${id}/translation`),
  researchTranslationStreamUrl: (id) =>
    withApiToken(`/api/external/research/${id}/translate/stream`),
  listHormuz: () => request("/api/external/hormuz"),
  getHormuz: (id) => request(`/api/external/hormuz/${id}`),
  createHormuz: async ({ title, body, file }) => {
    const fd = new FormData();
    fd.append("title", title);
    fd.append("body", body || "");
    if (file) fd.append("file", file);
    const res = await ensureOk(
      await apiFetch("/api/external/hormuz", { method: "POST", body: fd }),
    );
    return res.json();
  },
  hormuzFileUrl: (id) => withApiToken(`/api/external/hormuz/${id}/file`),
  deleteHormuz: async (id) => {
    await ensureOk(
      await apiFetch(`/api/external/hormuz/${id}`, { method: "DELETE" }),
    );
  },

  // Date-organized Hormuz source library + V3 bilingual appendix.
  hormuzLibrary: () => request("/api/external/hormuz/library"),
  uploadHormuzSources: async (fileList) => {
    const fd = new FormData();
    for (const f of fileList) fd.append("files", f);
    const res = await ensureOk(
      await apiFetch("/api/external/hormuz/sources", {
        method: "POST",
        body: fd,
      }),
    );
    return res.json();
  },
  hormuzSourceUrl: (date, filename) =>
    withApiToken(
      `/api/external/hormuz/sources/${date}/${encodeURIComponent(filename)}`,
    ),
  generateHormuzAppendix: async (date) => {
    const res = await ensureOk(
      await apiFetch(`/api/external/hormuz/appendix/${date}/generate`, {
        method: "POST",
      }),
    );
    return res.json();
  },
  hormuzAppendixFileUrl: (date, slot) =>
    withApiToken(`/api/external/hormuz/appendix/${date}/file?slot=${slot}`),

  // ---- Weekly hot-stock dashboard ----
  weeklyStocks: {
    get: () => request("/api/weekly-stocks", { timeoutMs: 15000 }),
    refresh: ({ force = false } = {}) => {
      const qs = force ? "?force=true" : "";
      return request(`/api/weekly-stocks/refresh${qs}`, {
        method: "POST",
        timeoutMs: 15000,
      });
    },
    streamUrl: () => withApiToken("/api/weekly-stocks/refresh/stream"),
  },

  // ---- Stock Research tracker workspace ----
  researchPages: {
    marketPulse: () =>
      request("/api/research-pages/market-pulse", { timeoutMs: 15000 }),
    evidenceMatrix: ({ companyId } = {}) => {
      const qs = companyId ? `?company_id=${encodeURIComponent(companyId)}` : "";
      return request(`/api/research-pages/evidence-matrix${qs}`, {
        timeoutMs: 15000,
      });
    },
    hypothesisLab: () =>
      request("/api/research-pages/hypothesis-lab", { timeoutMs: 15000 }),
  },

  // ---- Stock Research tracker workspace ----
  stockResearch: {
    dashboard: () => request("/api/stock-research", { timeoutMs: 15000 }),
    doctor: () => request("/api/stock-research/doctor", { timeoutMs: 15000 }),
    runLedger: () => request("/api/stock-research/run-ledger", { timeoutMs: 15000 }),
    listTrackers: ({ includeArchived = false } = {}) =>
      request(
        `/api/stock-research/trackers?include_archived=${includeArchived ? "true" : "false"}`,
      ),
    createTracker: (payload) =>
      request("/api/stock-research/trackers", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    updateTracker: (trackerId, patch) =>
      request(`/api/stock-research/trackers/${encodeURIComponent(trackerId)}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    disableTracker: (trackerId, { archive = false } = {}) =>
      request(
        `/api/stock-research/trackers/${encodeURIComponent(trackerId)}/disable?archive=${archive ? "true" : "false"}`,
        { method: "POST" },
      ),
    importCompanyTrackers: ({ limit = 20 } = {}) =>
      request(`/api/stock-research/trackers/import-companies?limit=${encodeURIComponent(limit)}`, {
        method: "POST",
      }),
    addLinkSource: (payload) =>
      request("/api/stock-research/sources/link", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    addNoteSource: (payload) =>
      request("/api/stock-research/sources/note", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    uploadSource: async ({ file, trackerIds, title, priority, relevance }) => {
      const fd = new FormData();
      fd.append("file", file);
      for (const id of trackerIds || []) fd.append("tracker_ids", id);
      if (title) fd.append("title", title);
      if (priority) fd.append("priority", priority);
      if (relevance) fd.append("relevance", relevance);
      const res = await ensureOk(
        await apiFetch("/api/stock-research/sources/upload", {
          method: "POST",
          body: fd,
        }),
      );
      return res.json();
    },
    runTracker: (trackerId, { periodId, force = false } = {}) => {
      const qs = new URLSearchParams();
      if (periodId) qs.set("period_id", periodId);
      if (force) qs.set("force", "true");
      const query = qs.toString();
      return request(
        `/api/stock-research/trackers/${encodeURIComponent(trackerId)}/run${query ? `?${query}` : ""}`,
        { method: "POST", timeoutMs: 15000 },
      );
    },
    runSelectedTrackers: (trackerIds, { retryFailed = true, periodId = null } = {}) =>
      request("/api/stock-research/trackers/run-selected", {
        method: "POST",
        body: JSON.stringify({
          tracker_ids: trackerIds,
          retry_failed: retryFailed,
          period_id: periodId,
        }),
        timeoutMs: 15000,
      }),
    runDueTrackers: ({ periodId = null } = {}) => {
      const qs = periodId ? `?period_id=${encodeURIComponent(periodId)}` : "";
      return request(`/api/stock-research/trackers/run-due${qs}`, {
        method: "POST",
        timeoutMs: 15000,
      });
    },
    cancelRun: (trackerId, runId) =>
      request(
        `/api/stock-research/trackers/${encodeURIComponent(trackerId)}/runs/${encodeURIComponent(runId)}/cancel`,
        { method: "POST" },
      ),
    retryRun: (trackerId, runId) =>
      request(
        `/api/stock-research/trackers/${encodeURIComponent(trackerId)}/runs/${encodeURIComponent(runId)}/retry`,
        { method: "POST", timeoutMs: 15000 },
      ),
    runAggregate: ({ periodId, force = false } = {}) => {
      const qs = new URLSearchParams();
      if (periodId) qs.set("period_id", periodId);
      if (force) qs.set("force", "true");
      const query = qs.toString();
      return request(`/api/stock-research/aggregates/run${query ? `?${query}` : ""}`, {
        method: "POST",
        timeoutMs: 15000,
      });
    },
    cancelAggregate: (periodId) =>
      request(`/api/stock-research/aggregates/${encodeURIComponent(periodId)}/cancel`, {
        method: "POST",
      }),
    retryAggregate: (periodId) =>
      request(`/api/stock-research/aggregates/${encodeURIComponent(periodId)}/retry`, {
        method: "POST",
        timeoutMs: 15000,
      }),
    runStrategyMap: ({ periodId, force = false } = {}) => {
      const qs = new URLSearchParams();
      if (periodId) qs.set("period_id", periodId);
      if (force) qs.set("force", "true");
      const query = qs.toString();
      return request(`/api/stock-research/strategy-maps/run${query ? `?${query}` : ""}`, {
        method: "POST",
        timeoutMs: 15000,
      });
    },
    cancelStrategyMap: (periodId) =>
      request(`/api/stock-research/strategy-maps/${encodeURIComponent(periodId)}/cancel`, {
        method: "POST",
      }),
    retryStrategyMap: (periodId) =>
      request(`/api/stock-research/strategy-maps/${encodeURIComponent(periodId)}/retry`, {
        method: "POST",
        timeoutMs: 15000,
      }),
    updateWorkProduct: (artifactId, patch) =>
      request(`/api/stock-research/work-products/${encodeURIComponent(artifactId)}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    updateReviewItem: (itemId, patch) =>
      request(`/api/stock-research/review-queue/${encodeURIComponent(itemId)}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    updateRunReview: (trackerId, runId, patch) =>
      request(
        `/api/stock-research/trackers/${encodeURIComponent(trackerId)}/runs/${encodeURIComponent(runId)}/review`,
        { method: "PATCH", body: JSON.stringify(patch) },
      ),
    reviewKnowledgeUpdate: (trackerId, runId, updateId, patch) =>
      request(
        `/api/stock-research/trackers/${encodeURIComponent(trackerId)}/runs/${encodeURIComponent(runId)}/knowledge/${encodeURIComponent(updateId)}`,
        { method: "PATCH", body: JSON.stringify(patch) },
      ),
    listHypotheses: () =>
      request("/api/stock-research/hypotheses", { timeoutMs: 15000 }),
    createHypotheses: ({
      vintageDate,
      vintageKind = "forward_live",
      allowDebugBackfill = false,
      horizonDays = 7,
    } = {}) =>
      request("/api/stock-research/hypotheses/create", {
        method: "POST",
        body: JSON.stringify({
          vintage_date: vintageDate,
          vintage_kind: vintageKind,
          allow_debug_backfill: allowDebugBackfill,
          horizon_days: horizonDays,
        }),
        timeoutMs: 15000,
      }),
    evaluateHypotheses: (vintageDate, payload = {}) =>
      request(
        `/api/stock-research/hypotheses/${encodeURIComponent(vintageDate)}/evaluate`,
        {
          method: "POST",
          body: JSON.stringify(payload),
          timeoutMs: 15000,
        },
      ),
    calibrateHypotheses: () =>
      request("/api/stock-research/hypotheses/calibrate", {
        method: "POST",
        timeoutMs: 15000,
      }),
  },

  listThreads: (companyId) =>
    request(`/api/companies/${companyId}/threads`),
  addThread: (companyId, payload) =>
    request(`/api/companies/${companyId}/threads`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // ---- Public-company trader snapshot ----
  // POST kicks off (or attaches to) a refresh; SSE streams claude_action
  // events; on `done`, the company record's trader_snapshot is fresh.
  trader: {
    // `opts.force === true` adds `?force=true`, which supersedes any
    // stale in-flight refresh. Used by the "Force refresh" affordance
    // surfaced after a breaking schema change (see docs/heat-card-v2.md).
    refresh: (companyId, opts = {}) => {
      const qs = opts.force ? "?force=true" : "";
      return request(
        `/api/companies/${companyId}/trader/refresh${qs}`,
        { method: "POST" },
      );
    },
    refreshSections: (companyId, sections, opts = {}) =>
      request(`/api/companies/${companyId}/trader/refresh-sections`, {
        method: "POST",
        body: JSON.stringify({
          sections,
          force: opts.force !== false,
          preserve_existing_sections: opts.preserveExistingSections !== false,
        }),
      }),
    refreshAll: (opts = {}) => {
      const qs = opts.force ? "?force=true" : "";
      return request(`/api/companies/trader/refresh-all${qs}`, {
        method: "POST",
        timeoutMs: 15000,
      });
    },
    stats: (limit = 60) =>
      request(`/api/trader/stats?limit=${encodeURIComponent(limit)}`, {
        timeoutMs: 15000,
      }),
    statsFor: (companyId, limit = 100) =>
      request(
        `/api/trader/stats/${companyId}?limit=${encodeURIComponent(limit)}`,
        { timeoutMs: 15000 },
      ),
    streamUrl: (companyId) =>
      withApiToken(`/api/companies/${companyId}/trader/refresh/stream`),
    refreshAllStreamUrl: () =>
      withApiToken("/api/companies/trader/refresh-all/stream"),
  },

  // ---- Console (per-company Q&A sessions) ----
  //
  // See docs/console-feature.md. All routes inherit the api_router auth
  // dependency; SSE URLs are wrapped with `withApiToken` so EventSource
  // can authenticate without setting headers.
  console: {
    listSessions: (companyId) =>
      request(`/api/companies/${companyId}/console/sessions`),
    estimate: (companyId, { include_background_docs = true, include_library_docs = true } = {}) => {
      const qs = new URLSearchParams({
        include_background_docs: include_background_docs ? "true" : "false",
        include_library_docs: include_library_docs ? "true" : "false",
      });
      return request(`/api/companies/${companyId}/console/estimate?${qs}`);
    },
    createSession: (
      companyId,
      {
        include_background_docs = true,
        include_library_docs = true,
        output_language = "en",
      } = {},
    ) =>
      request(`/api/companies/${companyId}/console/sessions`, {
        method: "POST",
        body: JSON.stringify({
          include_background_docs,
          include_library_docs,
          output_language,
        }),
      }),
    getSession: (companyId, sid) =>
      request(`/api/companies/${companyId}/console/sessions/${sid}`),
    getTurns: (companyId, sid) =>
      request(`/api/companies/${companyId}/console/sessions/${sid}/turns`),
    ask: async (companyId, sid, prompt, files = []) => {
      const fd = new FormData();
      fd.append("prompt", prompt);
      for (const f of files) fd.append("images", f, f.name);
      const res = await ensureOk(
        await apiFetch(
          `/api/companies/${companyId}/console/sessions/${sid}/ask`,
          { method: "POST", body: fd },
        ),
      );
      return res.json();
    },
    askStreamUrl: (companyId, sid, turnId) =>
      withApiToken(
        `/api/companies/${companyId}/console/sessions/${sid}/ask/stream/${turnId}`,
      ),
    hydrateStreamUrl: (companyId, sid) =>
      withApiToken(
        `/api/companies/${companyId}/console/sessions/${sid}/hydrate/stream`,
      ),
    cancelAsk: async (companyId, sid, turnId) => {
      const res = await apiFetch(
        `/api/companies/${companyId}/console/sessions/${sid}/ask/${turnId}/cancel`,
        { method: "POST" },
      );
      // A 404 means the turn already finished — treat as a no-op cancel.
      if (res.status !== 404) await ensureOk(res);
      return res.status === 204;
    },
    attachmentUrl: (companyId, sid, imgId) =>
      withApiToken(
        `/api/companies/${companyId}/console/sessions/${sid}/attachments/${imgId}`,
      ),
    archive: (companyId, sid) =>
      request(`/api/companies/${companyId}/console/sessions/${sid}/archive`, {
        method: "POST",
      }),
    deleteSession: async (companyId, sid) => {
      await ensureOk(
        await apiFetch(`/api/companies/${companyId}/console/sessions/${sid}`, {
          method: "DELETE",
        }),
      );
    },
  },

  copilot: {
    context: (companyId, body = {}) =>
      request(`/api/companies/${companyId}/copilot/context`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    ask: (companyId, body) =>
      request(`/api/companies/${companyId}/copilot/ask`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    // Stage a file beside Warren's session. Uploaded when it is picked, so
    // one he cannot read is refused before the question is sent; the ask
    // carries the returned `stored_name` back.
    attach: async (companyId, file, mode = "quick") => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mode", mode);
      const res = await ensureOk(
        await apiFetch(`/api/companies/${companyId}/copilot/attachments`, {
          method: "POST",
          body: fd,
        }),
      );
      return res.json();
    },
    // Warren's threads for this company — everyone's, not this browser's.
    threads: (companyId, mode = "quick") =>
      request(
        `/api/companies/${companyId}/copilot/threads?mode=${encodeURIComponent(mode)}`,
      ),
    // Files the current thread into the history and opens a fresh one.
    startThread: (companyId, body = {}) =>
      request(`/api/companies/${companyId}/copilot/threads`, {
        method: "POST",
        body: JSON.stringify({ mode: "quick", ...body }),
      }),
    createTask: (companyId, body) =>
      request(`/api/companies/${companyId}/copilot/tasks`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    applyEdit: (companyId, body) =>
      request(`/api/companies/${companyId}/copilot/apply-edit`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    recordEvent: (companyId, body) =>
      request(`/api/companies/${companyId}/copilot/events`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },

  // Hormuz Console — scoped to the last two days of Hormuz reports.
  // The fixed id "hormuz" reuses the generic, company-agnostic console
  // endpoints for everything except create (which stages Hormuz docs).
  hormuzConsole: {
    SCOPE: "hormuz",
    context: () => request("/api/external/hormuz/console/context"),
    createSession: ({ output_language = "en" } = {}) =>
      request("/api/external/hormuz/console/sessions", {
        method: "POST",
        body: JSON.stringify({ output_language }),
      }),
  },
};

export default api;
