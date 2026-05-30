// API auth. Two parallel paths:
//
//   1. Per-session bearer token (preferred). A future login UI will
//      POST /api/auth/token with {email,password} and stash the returned
//      session in localStorage under SESSION_KEY. While present and not
//      expired, every API call uses it.
//   2. Shared `BSH_RESEARCH_API_TOKEN` from the server-rendered <meta>
//      tag (legacy / "meta-tag" flow). Falls back to this when there's
//      no session in localStorage — keeps the current SPA working
//      unchanged until the login UI lands.
//
// `apiFetch` is the canonical wrapper — use it for any code path that
// hits /api/. For raw URLs (downloads, EventSource SSE), use
// `withApiToken(path)` instead since those don't support custom headers.

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
  const session = getSessionToken();
  if (session) return session;
  if (typeof document === "undefined") return null;
  const el = document.querySelector('meta[name="bsh-research-api-token"]');
  return el && el.content ? el.content : null;
}

export function withApiToken(path) {
  const url = withBase(path);
  const tok = getApiToken();
  if (!tok) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(tok)}`;
}

export function apiFetch(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const tok = getApiToken();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;
  return fetch(withBase(path), { ...opts, headers });
}

function _httpError(status, statusText, body) {
  const err = new Error(`${status} ${statusText}${body ? `: ${body}` : ""}`);
  err.status = status;
  return err;
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
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    if (res.status === 401 && typeof window !== "undefined") {
      // auth.js listens for this and clears the stale session so the
      // router guard kicks the user back to /login on next nav.
      window.dispatchEvent(new CustomEvent("bsh:unauthorized"));
    }
    throw _httpError(res.status, res.statusText, text);
  }
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
  listCompanyReports: (companyId) =>
    request(`/api/companies/${companyId}/reports`),
  listFiles: (companyId) => request(`/api/companies/${companyId}/files`),
  uploadFile: async (companyId, file, label, language) => {
    const fd = new FormData();
    fd.append("file", file);
    if (label) fd.append("label", label);
    if (language) fd.append("language", language);
    const res = await apiFetch(`/api/companies/${companyId}/files`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
    }
    return res.json();
  },
  fileUrl: (companyId, fileId) =>
    withApiToken(`/api/companies/${companyId}/files/${fileId}`),
  filePreviewUrl: (companyId, fileId) =>
    withApiToken(`/api/companies/${companyId}/files/${fileId}/preview`),
  deleteFile: async (companyId, fileId) => {
    const res = await apiFetch(`/api/companies/${companyId}/files/${fileId}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
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
  deleteFileSummary: async (companyId, fileId) => {
    const res = await apiFetch(
      `/api/companies/${companyId}/files/${fileId}/summary`,
      { method: "DELETE" },
    );
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  },

  // Research library (Serena's per-company background-docs folder).
  // Distinct from the Document Library above.
  listResearchFiles: (companyId) =>
    request(`/api/companies/${companyId}/research-files`),
  uploadResearchFile: async (companyId, file, label) => {
    const fd = new FormData();
    fd.append("file", file);
    if (label) fd.append("label", label);
    const res = await apiFetch(
      `/api/companies/${companyId}/research-files`,
      { method: "POST", body: fd },
    );
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
    }
    return res.json();
  },
  researchFileUrl: (companyId, fileId, opts = {}) =>
    withApiToken(
      `/api/companies/${companyId}/research-files/${fileId}${
        opts.inline ? "?inline=1" : ""
      }`,
    ),
  deleteResearchFile: async (companyId, fileId) => {
    const res = await apiFetch(
      `/api/companies/${companyId}/research-files/${fileId}`,
      { method: "DELETE" },
    );
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
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
    const res = await apiFetch(
      `/api/companies/${companyId}/research-files/${fileId}/summary`,
      { method: "DELETE" },
    );
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
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
    const res = await apiFetch(`/api/external/news/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  },
  retryNews: (id) =>
    request(`/api/external/news/${id}/retry`, { method: "POST" }),
  retryExternalResearch: (id) =>
    request(`/api/external/research/${id}/retry`, { method: "POST" }),
  diagnostics: () => request("/api/diagnostics"),
  listExternalResearch: () => request("/api/external/research"),
  getExternalResearch: (id) => request(`/api/external/research/${id}`),
  uploadExternalResearch: async (form) => {
    const res = await apiFetch("/api/external/research", {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
    }
    return res.json();
  },
  externalResearchFileUrl: (id, opts = {}) =>
    withApiToken(
      `/api/external/research/${id}/file${opts.inline ? "?inline=1" : ""}`,
    ),
  deleteExternalResearch: async (id) => {
    const res = await apiFetch(`/api/external/research/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
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
    const res = await apiFetch("/api/external/hormuz", {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
    }
    return res.json();
  },
  hormuzFileUrl: (id) => withApiToken(`/api/external/hormuz/${id}/file`),
  deleteHormuz: async (id) => {
    const res = await apiFetch(`/api/external/hormuz/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  },

  // Date-organized Hormuz source library + V3 bilingual appendix.
  hormuzLibrary: () => request("/api/external/hormuz/library"),
  uploadHormuzSources: async (fileList) => {
    const fd = new FormData();
    for (const f of fileList) fd.append("files", f);
    const res = await apiFetch("/api/external/hormuz/sources", {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
    }
    return res.json();
  },
  hormuzSourceUrl: (date, filename) =>
    withApiToken(
      `/api/external/hormuz/sources/${date}/${encodeURIComponent(filename)}`,
    ),
  generateHormuzAppendix: async (date) => {
    const res = await apiFetch(
      `/api/external/hormuz/appendix/${date}/generate`,
      { method: "POST" },
    );
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
    }
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
      const res = await apiFetch(
        `/api/companies/${companyId}/console/sessions/${sid}/ask`,
        { method: "POST", body: fd },
      );
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        let detail = null;
        try { detail = JSON.parse(text); } catch { /* keep raw text */ }
        const err = _httpError(res.status, res.statusText, text);
        err.detail = detail;
        throw err;
      }
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
      if (!res.ok && res.status !== 404) {
        throw _httpError(res.status, res.statusText, await res.text().catch(() => ""));
      }
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
      const res = await apiFetch(
        `/api/companies/${companyId}/console/sessions/${sid}`,
        { method: "DELETE" },
      );
      if (!res.ok) throw _httpError(res.status, res.statusText, await res.text().catch(() => ""));
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
