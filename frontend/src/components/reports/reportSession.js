// What the Reports surfaces need from the session, beyond the report itself:
// the reader's permissions (GET /api/auth/me → permissions), reading
// telemetry (POST /api/reports/{id}/events, fire and forget, once per
// browser session per report and language), and the link a report is
// shared by.

import { ref } from "vue";
import { api } from "../../api.js";

// null until /api/auth/me answers (or when it could not be read): controls
// that need a permission stay hidden until it is known.
export const sessionPermissions = ref(null);

let permissionsRequest = null;

/** Load the signed-in reader's permissions once; later calls share the answer. */
export function loadReportPermissions({ force = false } = {}) {
  if (permissionsRequest && !force) return permissionsRequest;
  permissionsRequest = (async () => {
    try {
      const me = await api.me();
      sessionPermissions.value = Array.isArray(me?.permissions) ? [...me.permissions] : [];
    } catch {
      sessionPermissions.value = null;
      // Let the next surface try again rather than caching a failure.
      permissionsRequest = null;
    }
    return sessionPermissions.value;
  })();
  return permissionsRequest;
}

// ---- Reading telemetry ---------------------------------------------------------

const OPENED_KEY = "bsh.reportsOpened";
const openedThisSession = new Set();

function readOpened() {
  try {
    const raw = window.sessionStorage.getItem(OPENED_KEY);
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function rememberOpened(key) {
  openedThisSession.add(key);
  try {
    const list = readOpened();
    if (!list.includes(key)) {
      list.push(key);
      window.sessionStorage.setItem(OPENED_KEY, JSON.stringify(list.slice(-200)));
    }
  } catch {
    // sessionStorage unavailable: the in-memory set still dedupes this page
  }
}

function send(reportId, event, options) {
  try {
    const pending = api.recordReportEvent(reportId, event, options);
    if (pending && typeof pending.catch === "function") pending.catch(() => {});
  } catch {
    // Telemetry never gets in a reader's way.
  }
}

/**
 * A report was opened in a language ("en" / "zh"; the IC memo sends none).
 * Recorded once per browser session per report and language; the server
 * dedupes per reader session as well. Returns whether an event was sent.
 */
export function recordReportOpened(reportId, language, source) {
  if (!reportId) return false;
  const key = `${reportId}|${language || "-"}`;
  if (openedThisSession.has(key) || readOpened().includes(key)) {
    openedThisSession.add(key);
    return false;
  }
  rememberOpened(key);
  send(reportId, "report_opened", { language: language || undefined, source });
  return true;
}

/** An explicit export: every one is recorded (the server logs the file too). */
export function recordReportDownloaded(reportId, language, source) {
  if (!reportId) return;
  send(reportId, "report_downloaded", { language: language || undefined, source });
}

// ---- Sharing -----------------------------------------------------------------------

/** The app's own link to a report in a language: <origin>/research/reports?id=…&lang=…. */
export function reportShareUrl(reportId, lang) {
  const base = String(import.meta.env.BASE_URL || "/");
  const params = new URLSearchParams({ id: String(reportId || "") });
  if (lang) params.set("lang", String(lang).toLowerCase());
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${base.endsWith("/") ? base : `${base}/`}reports?${params}`;
}

/** Copy text to the clipboard; resolves false when the browser refuses. */
export async function copyText(text) {
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the textarea route
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = typeof document.execCommand === "function" && document.execCommand("copy");
    area.remove();
    return Boolean(ok);
  } catch {
    return false;
  }
}

/** Test hook: forget the cached permissions and the opened set. */
export function resetReportSession() {
  sessionPermissions.value = null;
  permissionsRequest = null;
  openedThisSession.clear();
  try {
    window.sessionStorage.removeItem(OPENED_KEY);
  } catch {
    // ignore
  }
}
