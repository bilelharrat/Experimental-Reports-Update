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

  options: () => request("/api/options"),
  listCompanies: () => request("/api/companies"),
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
  listReports: () => request("/api/reports"),
  getReport: (id) => request(`/api/reports/${id}`),
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
  getCompanyIndustryView: (id) =>
    request(`/api/companies/${id}/industry-view`),
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
  resumeReport: (reportId) =>
    request(`/api/reports/${encodeURIComponent(reportId)}/resume`, {
      method: "POST",
    }),
  dismissReport: (reportId) =>
    request(`/api/reports/${encodeURIComponent(reportId)}/dismiss`, {
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
  uploadResearchFile: async (companyId, file, label) => {
    const fd = new FormData();
    fd.append("file", file);
    if (label) fd.append("label", label);
    const res = await ensureOk(
      await apiFetch(`/api/companies/${companyId}/research-files`, {
        method: "POST",
        body: fd,
      }),
    );
    return res.json();
  },
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
    get: (companyId) =>
      request(`/api/companies/${companyId}/memo-analysis`),
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
    moveCard: (companyId, sectionId, cardId, direction) =>
      request(
        `/api/companies/${companyId}/memo-editor/sections/${encodeURIComponent(sectionId)}/cards/${encodeURIComponent(cardId)}/move`,
        { method: "POST", body: JSON.stringify({ direction }) },
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
