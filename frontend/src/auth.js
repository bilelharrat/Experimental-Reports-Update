// Web login / session-token state.
//
// The SPA gates every non-/login route behind `isAuthenticated`. A
// successful POST /api/auth/token stashes the response in localStorage
// under SESSION_KEY (same key `getApiToken()` in api.js reads), and the
// route guard in router.js sends you to /login when there's no live
// session. A 401 from any /api/* call dispatches `bsh:unauthorized` —
// we listen for it here and tear the session down so the router bounces
// the user to /login on the next navigation.
//
// Local exception: when the server injects
// `<meta name="bsh-research-anon-dev" content="1">` (`BSH_ALLOW_ANON_DEV=1`),
// the SPA treats the operator as signed in with no stored session.

import { computed, ref } from "vue";
import { api, withBase } from "./api.js";
import { accountInitials, displayNameFromEmail } from "./formatters.js";

const SESSION_KEY = "bsh.research.session";

function _readStoredSession() {
  if (typeof window === "undefined" || !window.localStorage) return null;
  let raw;
  try {
    raw = window.localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  let s;
  try {
    s = JSON.parse(raw);
  } catch {
    window.localStorage.removeItem(SESSION_KEY);
    return null;
  }
  if (!s || !s.token) return null;
  if (s.expires_at) {
    const t = Date.parse(s.expires_at);
    if (Number.isFinite(t) && t <= Date.now()) {
      window.localStorage.removeItem(SESSION_KEY);
      return null;
    }
  }
  return s;
}

function _writeStoredSession(s) {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(s));
  } catch {
    // localStorage quota / private mode — session lives in memory only.
  }
}

function _clearStoredSession() {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // ignore
  }
}

export const session = ref(_readStoredSession());
export const sessionName = ref(null);

export function isAnonDev() {
  if (typeof document === "undefined") return false;
  const el = document.querySelector('meta[name="bsh-research-anon-dev"]');
  if (el?.content?.trim() === "1") return true;
  if (typeof window !== "undefined" && window.location) {
    const host = window.location.hostname;
    const port = window.location.port;
    if (
      (host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0") &&
      (port === "5173" || port === "5181" || port === "8010" || port === "8011")
    ) {
      return true;
    }
  }
  return false;
}

export const isAuthenticated = computed(
  () => session.value !== null || isAnonDev(),
);
export const sessionEmail = computed(() => session.value?.email ?? null);
export const sessionInitials = computed(() =>
  accountInitials(sessionName.value || session.value?.email, "?"),
);

function _applyIdentity(me) {
  if (!me || typeof me !== "object") return;
  const email = me.email || null;
  if (email && session.value && session.value.email !== email) {
    const next = { ...session.value, email };
    _writeStoredSession(next);
    session.value = next;
  }
  sessionName.value = me.name || (email ? displayNameFromEmail(email) : null) || null;
}

export async function signIn(email, password) {
  const res = await api.login(email, password);
  // Shape: { token, email, created_at, expires_at }
  _writeStoredSession(res);
  session.value = res;
  sessionName.value = displayNameFromEmail(res.email) || null;
  try {
    _applyIdentity(await api.me());
  } catch {
    // Login succeeded; identity enrichment is best-effort.
  }
  return res;
}

export async function signOut() {
  const had = session.value;
  // Clear local state first so the router guard kicks the user to
  // /login immediately, even if the network call below hangs.
  _clearStoredSession();
  session.value = null;
  sessionName.value = null;
  if (had?.token) {
    // Post directly with the captured token (local state is already
    // cleared, so apiFetch would send no Authorization header). Include
    // credentials so the server can also clear the session cookie.
    try {
      await fetch(withBase("/api/auth/logout"), {
        method: "POST",
        headers: { Authorization: `Bearer ${had.token}`, "X-BSH-Client": "web" },
        credentials: "same-origin",
      });
    } catch {
      // Network blip / server already gone — local state is gone too.
    }
  }
}

// Called by router on boot: confirm a stored token still works, and always
// hydrate display name/initials (including anon-dev operator identity).
export async function validateSession() {
  if (!session.value && !isAnonDev()) return false;
  try {
    const me = await api.me();
    _applyIdentity(me);
    return Boolean(session.value);
  } catch (e) {
    if (e && e.status === 401) {
      _clearStoredSession();
      session.value = null;
      sessionName.value = null;
    }
    return false;
  }
}

if (typeof window !== "undefined") {
  // api.js dispatches this on every 401 — covers expired/revoked
  // tokens mid-session without each caller having to handle it.
  window.addEventListener("bsh:unauthorized", () => {
    if (session.value !== null) {
      _clearStoredSession();
      session.value = null;
      sessionName.value = null;
    }
  });
}
