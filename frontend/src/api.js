// API auth. When the server has `BSH_RESEARCH_API_TOKEN` configured it
// injects the value into the served HTML via this meta tag; we forward
// the token on every API call. `apiFetch` is the canonical wrapper —
// use it for any code path that hits /api/. For raw URLs (downloads,
// EventSource SSE), use `withApiToken(path)` instead since those don't
// support custom headers.

function getApiToken() {
  if (typeof document === "undefined") return null;
  const el = document.querySelector('meta[name="bsh-research-api-token"]');
  return el && el.content ? el.content : null;
}

export function withApiToken(path) {
  const tok = getApiToken();
  if (!tok) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}token=${encodeURIComponent(tok)}`;
}

export function apiFetch(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const tok = getApiToken();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;
  return fetch(path, { ...opts, headers });
}

async function request(path, opts = {}) {
  const res = await apiFetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
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
  listActiveJobs: () => request("/api/jobs/active"),
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
  listThreads: (companyId) =>
    request(`/api/companies/${companyId}/threads`),
  addThread: (companyId, payload) =>
    request(`/api/companies/${companyId}/threads`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
