async function request(path, opts = {}) {
  const res = await fetch(path, {
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
  selectCompany: (payload) =>
    request("/api/companies/select", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getCompany: (id) => request(`/api/companies/${id}`),
  generateReport: (payload) =>
    request("/api/reports", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listCompanyReports: (companyId) =>
    request(`/api/companies/${companyId}/reports`),
  listFiles: (companyId) => request(`/api/companies/${companyId}/files`),
  uploadFile: async (companyId, file, label) => {
    const fd = new FormData();
    fd.append("file", file);
    if (label) fd.append("label", label);
    const res = await fetch(`/api/companies/${companyId}/files`, {
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
    `/api/companies/${companyId}/files/${fileId}`,
  deleteFile: async (companyId, fileId) => {
    const res = await fetch(`/api/companies/${companyId}/files/${fileId}`, {
      method: "DELETE",
    });
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
